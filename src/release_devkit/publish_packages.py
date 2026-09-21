from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from pydantic_settings import BaseSettings
from ci_devkit.ci_step import ci_step
from ci_devkit.setup import configure_git, free_disk_space, install_dotnet, install_node

from .config import load_config, select_packages
from .feeds import PublishRequest, build_feeds
from .ledger import GitLedger
from .plan import compute_plan, next_version, render_summary, resolved_dependency_versions

app = typer.Typer(add_completion=False, pretty_exceptions_show_locals=False)

DEFAULT_CONFIG_PATH = Path("build/publish-config.json")


class Settings(BaseSettings):
    github_workspace: str = ""
    github_step_summary: str | None = None
    github_output: str | None = None
    nuget_api_key: str = ""


def _append_output(path: str | None, line: str) -> None:
    if path:
        with Path(path).open("a", encoding="utf-8") as file:
            file.write(line + "\n")


@app.command()
def main(
    config: Annotated[Path, typer.Option(help="Publish configuration JSON")] = DEFAULT_CONFIG_PATH,
    dry_run: Annotated[bool, typer.Option(help="Plan publishes without executing them")] = False,
    only: Annotated[list[str] | None, typer.Option(help="Restrict to named packages (repeatable).")] = None,
    exclude: Annotated[list[str] | None, typer.Option(help="Skip named packages (repeatable).")] = None,
    with_apps: Annotated[bool, typer.Option(help="Handle app version bumps and tags in a filtered run.")] = False,
) -> None:
    settings = Settings.model_validate({})
    publish_config = load_config(config)
    packages = select_packages(publish_config.packages, only or [], exclude or [])
    ledger = GitLedger()

    with ci_step("Compute publish plan"):
        plans = compute_plan(publish_config.packages, ledger)

        summary = render_summary(plans)
        print(summary)
        _append_output(settings.github_step_summary, summary)

        if not any(plan.publish for plan in plans.values()):
            print("Nothing to publish")
            return

        if dry_run:
            print("Dry run — skipping publish")
            return

    with ci_step("Setup"):
        configure_git(settings.github_workspace)
        free_disk_space()
        install_dotnet("8.0")
        install_node("24", "https://registry.npmjs.org")

    feeds = build_feeds(settings.nuget_api_key)
    for package in packages:
        plan = plans[package.name]
        if not plan.publish:
            continue
        dependency_versions = resolved_dependency_versions(package, plans)
        for feed_name, identity in package.feeds.items():
            with ci_step(f"Publish {feed_name} ({package.name})"):
                feeds[feed_name].publish(
                    PublishRequest(
                        path=package.path,
                        identity=identity,
                        version=plan.version,
                        dependency_versions=dependency_versions,
                    )
                )

    handle_apps = (not only and not exclude) or with_apps
    any_package_published = any(plans[package.name].publish for package in packages)
    app_versions: dict[str, str] = {}
    with ci_step("Compute app versions"):
        for app_config in publish_config.apps:
            last_version = ledger.latest_version(f"{app_config.tag_prefix}-v")
            changed = ledger.has_changes_since(
                f"{app_config.tag_prefix}-v{last_version}" if last_version else None, app_config.path
            )
            # Apps depend on packages — bump if any package changed
            if any_package_published:
                changed = True
            if changed:
                new_version = next_version(last_version)
                app_versions[app_config.name] = new_version
                print(f"  {app_config.name}: {last_version or '(none)'} -> {new_version}")
            else:
                print(f"  {app_config.name}: {last_version or '0.0.0'} (unchanged)")

    with ci_step("Create version tags"):
        for package in packages:
            plan = plans[package.name]
            if plan.publish:
                tag = f"{package.name}-v{plan.version}"
                ledger.create_and_push_tag(tag)
                print(f"  Tagged: {tag}")

        if handle_apps:
            for app_config in publish_config.apps:
                if app_config.name in app_versions:
                    tag = f"{app_config.tag_prefix}-v{app_versions[app_config.name]}"
                    ledger.create_and_push_tag(tag)
                    print(f"  Tagged: {tag}")

        _append_output(settings.github_output, "published=true")
