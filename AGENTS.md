# release-devkit

## What this is

The publication machinery for outernet-foundation repos: the publish pipeline, the per-package tag ledger and path-diff change detection, ephemeral version patching, release orchestration, and the OCI mirror scan. A standalone repo (sibling of `unity-devkit` / `docker-devkit` / `bashrun`), published to PyPI and consumed **uvx-isolated** — it is a project dependency of nothing. The reason is structural: every tool repo it publishes sits inside its own dependency graph (bashrun, docker-devkit, unity-devkit are release-devkit's runtime deps), so a project-level release-devkit edge in those repos is a resolver cycle plus a root-version conflict against the `0.0.0.dev0` sentinel. Consumers outside that graph (placeframe) use uvx for the same shape, keeping one consumption model. Publish jobs in consumer repos run the **publish composite action** shipped here (`.github/actions/publish`, pinned to a pushed SHA): the action performs the same uvx invocation inside the caller's job, so the OIDC trusted-publishing identity stays the caller's own workflow file — PyPI hard-blocks reusable-workflow publishers (warehouse#11096) and npm binds the caller's top-level workflow filename, which is why publication ships as a composite action, never a reusable workflow. The uvx version pin lives inside the action; bumping it is an action-SHA bump at consumers.

The consumer owns everything declarative: package identities, paths, tag prefixes, registry mappings, compose files, and the CI workflow name live in a consumer-authored `publish-config.json`; every command here reads that file. Per-repo copies of this machinery are refused, as are per-ecosystem splits — the seam is internal: one `Feed` adapter per registry over the shared ledger/diff/versioning core.

The package is `release-devkit` (src-layout under `src/release_devkit/`; import `release_devkit`). Name history: `pubpkg` was unclaimable (PyPI's registrar rejects names merely similar to existing ones; nothing ever carried it), so `release-kit` was the first live PyPI identity — then the repo renamed to `release-devkit` (2026-09-21, member of the `-devkit` family): fresh tag ledger starting at `0.1.0`, with a terminal `release-kit` ≤0.1.0 deprecation release pointing here. Runtime dependencies: `bashrun` (all shell-outs), `docker-devkit` (`compute_service_shas`, `collect_repo_references`), `ci-devkit` (`ci_step`, runner setup, git-tag ledger), `pydantic`/`pydantic-settings` (config + CI env), `typer` (CLIs) — all from PyPI.

## Self-publication

release-devkit publishes itself from its own checkout: `release.yml` — triggered by a successful CI run on a `main` push — runs `uv run publish-packages --config publish-config.json`; the repo *is* release-devkit, so no uvx bootstrap and no self-reference. Its dependencies must all exist on PyPI before it publishes (leaves-first ordering: docker-devkit and unity-devkit publish before release-devkit repins to them). The committed `pyproject.toml` version is permanently the `0.0.0.dev0` sentinel; the `release-devkit-v*` tags are the version ledger. API-breaking changes ship with a manually bumped version — patch-auto assumes additive changes.

## Commands

All are `uv run <name> --config <path>` from the consuming repo's root (config defaults to `build/publish-config.json` where optional).

| Command | Role |
|---|---|
| `publish-packages` | Compute the publish plan from the tag ledger + path-diff, publish every changed package to its feeds, bump and tag app versions, push per-package tags. `--dry-run` prints the plan only. |
| `publish-dev` | Dev-channel mode: publish immutable `-dev.<run-id>` prereleases of every path-diff-changed package to its feeds. `--run-id` defaults to `GITHUB_RUN_ID`; never creates git tags, never touches app versions. |
| `create-release` | Assemble release notes (service SHAs from the configured compose files, package versions with registry links, app versions), package CI artifacts, and cut the dated GitHub Release. |
| `ensure-release-pr` | Maintain the standing `dev` → `main` "Next release" gate PR. |
| `fetch-ci-artifacts` | Locate the successful CI run for the release SHA (via the merge commit's second parent) and download its artifacts, pruning non-release ones per the config's skip rules. |
| `mirror-images` | Populate the org-level ghcr mirror namespace with every mirror-prefixed image reference the repo scan finds, via `crane copy`. |

## The CI-commit-free invariants

CI and release workflows must not create commits on any branch — `dev` → `main` merges are always true fast-forwards. The machinery that makes that possible lives here:

- **Version tracking**: per-package git tags (`{name}-v{semver}`, e.g. `placeframe-api-client-v0.1.8`, `capture-tool-v0.2.0`), never committed state files.
- **Change detection**: `git diff --quiet <last-tag> HEAD -- <path>`, never content hashing. `depends_on` cascades trigger dependents even when their own paths are unchanged.
- **Version scheme**: first release `0.1.0`, then patch bumps from the tag ledger. Per-package numbers are independent within one release event — no lockstep.
- **Unity `package.json` versions**: permanently `0.0.0-local` in the repo; patched ephemerally during `npm publish` and restored immediately — never committed.
- **Python `pyproject.toml` versions**: permanently `0.0.0.dev0` in the repo (`0.0.0-local` is not valid PEP 440); patched ephemerally around `uv build` and restored immediately — never committed. The sdist/wheel carries the real version; the committed file never does.

## Release units

The repo is the release unit: repos release independently; one release event publishes every changed package in the repo together; a package unchanged since its last tag is skipped (registries are immutable — there is nothing to publish), and dependency pins absorb sibling bumps without republishing dependents.

## Dev channel

`publish-dev` publishes immutable prereleases of every path-diff-changed package; it creates no git tags, bumps no app versions, and opens no release. Versions are keyed by the CI run id and spelled per feed — `{base}-dev.{run_id}` where semver allows it (nuget, npm), `{base}.dev{run_id}` on PyPI — because no single string is both valid semver and valid PEP 440. The base is `next_version(last stable tag)`, so a package's dev versions share one base until the stable flow tags it. npm prereleases ride the single inert `dev` dist-tag so `latest` never moves. The job prints the exact published versions; that print is the consumption interface — consumers pin by hand, there is no discovery tooling.

## The Feed seam

`feeds.Feed` is the registry adapter protocol (`publish(request: PublishRequest)`); `NuGetFeed`, `NpmFeed`, and `PyPIFeed` implement it. A feed's registry identity (nuget package id, npm name, PyPI distribution name) is config data, not code — the same package can publish to several feeds at one version. Config-declared feed names are validated against `feeds.KNOWN_FEEDS` at load time.

`PyPIFeed` shells out to `uv build` + `uv publish` and authenticates via trusted publishing (OIDC): it takes no credential, so the consuming workflow needs `id-token: write` and the PyPI project needs a configured (or pending) publisher for that repo/workflow. Idempotent re-publishing is handled by `uv publish --check-url` against the simple index. PyPI dependency pins are refused (`dependency_versions` must be empty) until a concrete in-repo consumer exists. npm authenticates the same way — trusted publishing via `--provenance`, no token plumbing — and npm allows one trusted publisher per package, bound to a single workflow filename: every workflow that publishes a given package to npm must be the same file.

## Config

`config.PublishConfig` (pydantic, loaded by `load_config`) validates the consumer's `publish-config.json`, including dependency-graph sanity: `depends_on` entries must reference packages declared **earlier** in the list (the plan walks dependencies-first), and `dependency_pins` must reference known packages. `dependency_pins` map a manifest dependency name to a package name; the pin is applied only when both the pinning package and the pinned package publish in the same event.

## See also

- `README.md` — human-facing usage and consumption wiring.
- [`bashrun`](https://github.com/outernet-foundation/bashrun) — the subprocess wrapper every shell-out goes through.
