from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Annotated

import typer
from bashrun.bash import bash, bash_output
from pydantic_settings import BaseSettings
from docker_devkit.context_sha import compute_service_shas
from ci_devkit.ci_step import ci_step

from .config import PublishConfig, load_config
from .ledger import GitLedger
from .plan import UNCHANGED_FALLBACK_VERSION

app = typer.Typer(add_completion=False, pretty_exceptions_show_locals=False)


class Settings(BaseSettings):
    github_repository: str


@app.command()
def main(config: Annotated[Path, typer.Option(help="Publish configuration JSON")]) -> None:
    settings = Settings.model_validate({})
    publish_config = load_config(config)
    tag = _next_release_tag(settings.github_repository)

    with ci_step("Compute service SHAs"):
        service_shas: dict[str, str] = {}
        for compose_file in publish_config.compose_files:
            service_shas.update(compute_service_shas(Path.cwd(), Path(compose_file)))
        for var, sha in sorted(service_shas.items()):
            print(f"  {var}={sha}")

    with ci_step("Package artifacts"):
        assets = _package_artifacts(publish_config)
        if assets:
            print(f"  {len(assets)} asset(s) ready for upload")
        else:
            print("  No build artifacts to attach")

    with ci_step("Create GitHub Release"):
        owner, repository = settings.github_repository.split("/", maxsplit=1)
        ghcr_url = f"https://github.com/orgs/{owner}/packages?repo_name={repository}"
        notes = _build_release_notes(publish_config, service_shas, ghcr_url)
        print(notes)

        asset_args = " ".join(f'"{a}"' for a in assets)
        with NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as file:
            file.write(notes)
            notes_path = file.name
        bash(
            f"gh release create {tag} --title {tag}"
            f" --notes-file {notes_path}"
            f" --repo {settings.github_repository}"
            f" {asset_args}"
        )
        Path(notes_path).unlink()
        print(f"  Release created: {tag}")


def _next_release_tag(repo: str) -> str:
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    existing = bash_output(
        f"gh release list --repo {repo} --json tagName --jq '[.[].tagName] | map(select(startswith(\"{today}\"))) | length'"
    ).strip()
    count = int(existing) if existing else 0
    return f"{today}.{count + 1}" if count > 0 else today


def _package_artifacts(config: PublishConfig) -> list[Path]:
    artifact_dir = config.artifact_dir
    assets: list[Path] = []
    if not artifact_dir.is_dir():
        print("No release artifacts directory found")
        return assets

    for entry in sorted(artifact_dir.iterdir()):
        if not entry.is_dir():
            continue
        if any(entry.name.startswith(p) for p in config.artifact_skip_prefixes):
            print(f"  Skipping: {entry.name} (not a release artifact)")
            continue
        if any(entry.name.endswith(s) for s in config.artifact_skip_suffixes):
            print(f"  Skipping: {entry.name} (not a release artifact)")
            continue

        files = [f for f in entry.rglob("*") if f.is_file()]
        if not files:
            print(f"  Skipping: {entry.name} (empty)")
            continue

        if len(files) == 1:
            asset = artifact_dir / f"{entry.name}{files[0].suffix}"
            shutil.copy2(files[0], asset)
            assets.append(asset)
            print(f"  Asset: {asset.name}")
        else:
            zip_path = artifact_dir / entry.name
            shutil.make_archive(str(zip_path), "zip", entry)
            asset = zip_path.parent / f"{zip_path.name}.zip"
            assets.append(asset)
            print(f"  Asset: {asset.name} ({len(files)} files)")

    return assets


def _nuget_url(identity: str, version: str) -> str:
    return f"https://www.nuget.org/packages/{identity}/{version}"


def _npm_url(identity: str, version: str) -> str:
    return f"https://www.npmjs.com/package/{identity}/v/{version}"


def _pypi_url(identity: str, version: str) -> str:
    return f"https://pypi.org/project/{identity}/{version}"


FEED_URLS = {"nuget": _nuget_url, "npm": _npm_url, "pypi": _pypi_url}


def _build_release_notes(config: PublishConfig, service_shas: dict[str, str], ghcr_url: str) -> str:
    ledger = GitLedger()
    lines: list[str] = []

    if service_shas:
        lines.extend([
            "## Docker images",
            "",
            f"Images on [GHCR]({ghcr_url}), per-service tags:",
            "",
            "| Env var | Tag |",
            "|---|---|",
        ])
        for var, sha in sorted(service_shas.items()):
            lines.append(f"| `{var}` | `{sha}` |")
        lines.append("")

    lines.extend(["## Packages", "", "| Package | Version | Registry |", "|---|---|---|"])
    for package in config.packages:
        version = ledger.latest_version(f"{package.name}-v") or UNCHANGED_FALLBACK_VERSION
        links: list[str] = []
        for feed_name, identity in package.feeds.items():
            url_builder = FEED_URLS.get(feed_name)
            if url_builder is None:
                links.append(feed_name)
            elif version != UNCHANGED_FALLBACK_VERSION:
                links.append(f"[{feed_name}]({url_builder(identity, version)})")
            else:
                links.append(feed_name)
        display = package.name
        lines.append(f"| {display} | {version} | {', '.join(links)} |")

    for app_config in config.apps:
        version = ledger.latest_version(f"{app_config.tag_prefix}-v")
        if version:
            lines.append(f"| {app_config.display_name} | {version} | — |")

    lines.append("")
    return "\n".join(lines)
