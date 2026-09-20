# pubpkg

Publication machinery for multi-feed package releases: a per-package git-tag ledger, path-diff change detection, ephemeral version patching, per-registry feed adapters (nuget, npm/UPM, PyPI), release orchestration, and an OCI mirror scan — all driven by a declarative, consumer-owned config.

Every consuming repo keeps only a `publish-config.json` (package identities, paths, tag prefixes, registry mappings) and workflow steps that are thin `uv run` invocations. See [`AGENTS.md`](./AGENTS.md) for the invariants (CI-commit-free releases, tag-ledger versioning, ephemeral `0.0.0-local` / `0.0.0.dev0` version patching) and the command catalog.

## Requirements

- Python 3.13+ and [uv](https://docs.astral.sh/uv/)
- At runtime: `git`, `gh`, `dotnet` (nuget publish), `node`/`npm` (npm publish), `uv` (PyPI publish via trusted publishing), `crane` (installed by `mirror-images`)

## Consuming from another repo

git-reference the package and declare its siblings' sources alongside it (uv's `[tool.uv.sources]` are not transitive):

```toml
[project]
dependencies = ["pubpkg"]

[tool.uv.sources]
pubpkg = { git = "https://github.com/outernet-foundation/pubpkg.git", rev = "<pin-a-commit-sha>" }
bashrun = { git = "https://github.com/outernet-foundation/bashrun.git", rev = "<pin-a-commit-sha>" }
stack-lifecycle = { git = "https://github.com/outernet-foundation/stack-lifecycle.git", rev = "<pin-a-commit-sha>" }
unity-buildkit = { git = "https://github.com/outernet-foundation/unity-buildkit.git", rev = "<pin-a-commit-sha>" }
```

Then author `build/publish-config.json`:

```json
{
  "packages": [
    { "name": "my-api-client", "path": "generated/csharp/api-client/src/MyApiClient",
      "feeds": { "nuget": "MyApiClient", "npm": "org.example.myproject.apiclient" } },
    { "name": "my-core", "path": "packages/unity/Core", "feeds": { "npm": "org.example.myproject" } },
    { "name": "my-arfoundation", "path": "packages/unity/ARFoundation",
      "feeds": { "npm": "org.example.myproject.arfoundation" },
      "depends_on": ["my-core"],
      "dependency_pins": { "org.example.myproject": "my-core" } }
  ],
  "apps": [
    { "name": "MyTool", "path": "apps/MyTool", "tag_prefix": "my-tool", "display_name": "My Tool" }
  ],
  "compose_files": ["compose.bake.yml"],
  "ci_workflow": "my-ci.yml",
  "mirror_prefix": "ghcr.io/my-org/mirror"
}
```

and invoke from CI:

```bash
uv run --no-sync publish-packages --config build/publish-config.json
uv run --no-sync publish-dev --config build/publish-config.json --run-id ${{ github.event.workflow_run.id }}
uv run --no-sync create-release --config build/publish-config.json
```

`publish-dev` is the dev-channel job: it publishes immutable `-dev.<run-id>` prereleases (`X.Y.Z.dev<run-id>` on PyPI) of every changed package on a green push — no git tags, npm `latest` untouched — and prints the exact versions to pin.

Environment (via pydantic-settings): `GITHUB_WORKSPACE`, `GITHUB_REPOSITORY`, `GITHUB_SHA`, `GITHUB_STEP_SUMMARY`, `GITHUB_OUTPUT`, `GITHUB_RUN_ID`, `NUGET_API_KEY`.

## Development

```bash
uv run ruff check .
uv run ruff format --check .
uv run basedpyright
uv run pytest
```
