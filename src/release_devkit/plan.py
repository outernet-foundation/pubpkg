from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .config import PackageConfig
from .feeds import DEV_VERSION_FORMATS

FIRST_VERSION = "0.1.0"
UNCHANGED_FALLBACK_VERSION = "0.0.0"


class TagLedger(Protocol):
    def latest_version(self, prefix: str) -> str | None: ...

    def has_changes_since(self, tag: str | None, path: Path) -> bool: ...


@dataclass(frozen=True)
class PackagePlan:
    name: str
    publish: bool
    version: str
    last_version: str | None


def compute_plan(packages: list[PackageConfig], ledger: TagLedger) -> dict[str, PackagePlan]:
    plans: dict[str, PackagePlan] = {}
    for package in packages:
        last_version = ledger.latest_version(f"{package.name}-v")
        changed = ledger.has_changes_since(f"{package.name}-v{last_version}" if last_version else None, package.path)
        if any(plans[dependency].publish for dependency in package.depends_on):
            changed = True
        plans[package.name] = PackagePlan(
            name=package.name,
            publish=changed,
            version=next_version(last_version) if changed else (last_version or UNCHANGED_FALLBACK_VERSION),
            last_version=last_version,
        )
    return plans


def next_version(last_version: str | None) -> str:
    if last_version is None:
        return FIRST_VERSION
    major, minor, patch = last_version.split(".")
    return f"{major}.{minor}.{int(patch) + 1}"


def resolved_dependency_versions(package: PackageConfig, plans: dict[str, PackagePlan]) -> dict[str, str]:
    return {
        dependency_name: plans[pinned_package].version
        for dependency_name, pinned_package in package.dependency_pins.items()
        if plans[pinned_package].publish
    }


def render_summary(plans: dict[str, PackagePlan]) -> str:
    lines = [
        "### Publish Plan",
        "| Package | Publish | Version |",
        "|---|---|---|",
    ]
    lines.extend(f"| {plan.name} | {plan.publish} | {plan.version} |" for plan in plans.values())
    return "\n".join(lines)


def render_dev_summary(packages: list[PackageConfig], plans: dict[str, PackagePlan], run_id: str) -> str:
    lines = [
        "### Dev Publish Plan",
        "| Package | Publish | Versions |",
        "|---|---|---|",
    ]
    for package in packages:
        plan = plans[package.name]
        if not plan.publish:
            lines.append(f"| {plan.name} | False | - |")
            continue
        versions = ", ".join(
            f"{feed_name}: {identity} @ {DEV_VERSION_FORMATS[feed_name](plan.version, run_id)}"
            for feed_name, identity in package.feeds.items()
        )
        lines.append(f"| {plan.name} | True | {versions} |")
    return "\n".join(lines)
