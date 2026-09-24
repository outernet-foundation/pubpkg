# release-devkit

Publication machinery for multi-feed package releases: a per-package git-tag ledger, path-diff change detection, ephemeral version patching, per-registry feed adapters (nuget, npm/UPM, PyPI), release orchestration, and an OCI mirror scan — all driven by a declarative, consumer-owned config.

Every consuming repo keeps only a `publish-config.json` (package identities, paths, version lines, tag prefixes, registry mappings) and workflow steps that are thin `uvx` invocations. See [`AGENTS.md`](./AGENTS.md) for the invariants (CI-commit-free releases, tag-ledger versioning, ephemeral `0.0.0-local` / `0.0.0.dev0` version patching) and the command catalog.

## Requirements

- Python 3.13+ and [uv](https://docs.astral.sh/uv/)
- At runtime: `git`, `gh`, `dotnet` (nuget publish), `node`/`npm` (npm publish), `uv` (PyPI publish via trusted publishing), `crane` (installed by `mirror-images`)

## Consuming from another repo

Install nothing — release-devkit is consumed **uvx-isolated** (it is a project dependency of nothing: the tool repos it publishes sit inside its own dependency graph, where a project-level release-devkit edge is a resolver cycle). Publish jobs inline the invocation as plain steps in the caller's workflow:

```yaml
jobs:
  publish:
    permissions:
      contents: write
      id-token: write
    steps:
      - uses: actions/checkout@v5

      # Workaround: fetch-tags is broken with shallow clones
      - run: git fetch --tags origin

      - uses: astral-sh/setup-uv@v7

      - name: Publish
        run: uvx --from release-devkit==0.1.11 publish-stable --config publish-config.json
```

The uvx invocation runs inside the caller's job, so the OIDC trusted-publishing identity stays the caller's own workflow — PyPI hard-blocks reusable-workflow publishers, which is why the call inlines in the caller's workflow rather than riding a reusable workflow. Direct uvx is the same shape anywhere else:

```bash
uvx --from release-devkit==0.1.11 publish-stable --config build/publish-config.json
```

Then author `build/publish-config.json`:

```json
{
  "packages": [
    { "name": "my-api-client", "path": "generated/csharp/api-client/src/MyApiClient",
      "major_minor": "0.1",
      "feeds": { "nuget": "MyApiClient", "npm": "org.example.myproject.apiclient" } },
    { "name": "my-core", "path": "packages/unity/Core", "major_minor": "1.0",
      "feeds": { "npm": "org.example.myproject" } },
    { "name": "my-arfoundation", "path": "packages/unity/ARFoundation", "major_minor": "1.0",
      "feeds": { "npm": "org.example.myproject.arfoundation" },
      "depends_on": ["my-core"],
      "dependency_pins": { "org.example.myproject": "my-core" } }
  ],
  "apps": [
    { "name": "MyTool", "path": "apps/MyTool", "major_minor": "1.0",
      "tag_prefix": "my-tool", "display_name": "My Tool" }
  ],
  "compose_files": ["compose.bake.yml"],
  "ci_workflow": "my-ci.yml",
  "mirror_prefix": "ghcr.io/my-org/mirror"
}
```

and invoke from CI:

```bash
uvx --from release-devkit==0.1.11 publish-stable --config build/publish-config.json
uvx --from release-devkit==0.1.11 publish-dev --config build/publish-config.json --run-id ${{ github.event.workflow_run.id }}
uvx --from release-devkit==0.1.11 create-release --config build/publish-config.json
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
