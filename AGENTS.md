# pubpkg

## What this is

The publication machinery for outernet-foundation repos: the publish pipeline, the per-package tag ledger and path-diff change detection, ephemeral version patching, release orchestration, and the OCI mirror scan. A standalone repo (sibling of `unity-buildkit` / `stack-lifecycle` / `bashrun`), consumed as a git-referenced dependency — its entry points install into the consumer's venv and CI workflows invoke them via `uv run <command>`.

The consumer owns everything declarative: package identities, paths, tag prefixes, registry mappings, compose files, and the CI workflow name live in a consumer-authored `publish-config.json`; every command here reads that file. Per-repo copies of this machinery are refused, as are per-ecosystem splits — the seam is internal: one `Feed` adapter per registry over the shared ledger/diff/versioning core.

The package is `pubpkg` (src-layout under `src/pubpkg/`). Runtime dependencies: `bashrun` (all shell-outs), `stack-lifecycle` (`compute_service_shas`, `collect_repo_references`), `unity-buildkit` (`ci_step`, runner setup), `pydantic`/`pydantic-settings` (config + CI env), `typer` (CLIs).

## Commands

All are `uv run <name> --config <path>` from the consuming repo's root (config defaults to `build/publish-config.json` where optional).

| Command | Role |
|---|---|
| `publish-packages` | Compute the publish plan from the tag ledger + path-diff, publish every changed package to its feeds, bump and tag app versions, push per-package tags. `--dry-run` prints the plan only. |
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

## Release units

The repo is the release unit: repos release independently; one release event publishes every changed package in the repo together; a package unchanged since its last tag is skipped (registries are immutable — there is nothing to publish), and dependency pins absorb sibling bumps without republishing dependents.

## The Feed seam

`feeds.Feed` is the registry adapter protocol (`publish(request: PublishRequest)`); `NuGetFeed` and `NpmFeed` implement it today and further registries (PyPI) join `build_feeds` as adapters over the same core. A feed's registry identity (nuget package id, npm name) is config data, not code — the same package can publish to several feeds at one version.

## Config

`config.PublishConfig` (pydantic, loaded by `load_config`) validates the consumer's `publish-config.json`, including dependency-graph sanity: `depends_on` entries must reference packages declared **earlier** in the list (the plan walks dependencies-first), and `dependency_pins` must reference known packages. `dependency_pins` map a manifest dependency name to a package name; the pin is applied only when both the pinning package and the pinned package publish in the same event.

## See also

- `README.md` — human-facing usage and consumption wiring.
- [`bashrun`](https://github.com/outernet-foundation/bashrun) — the subprocess wrapper every shell-out goes through.
