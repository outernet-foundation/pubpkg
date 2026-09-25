from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .config import PackageConfig
from .registries import DEV_VERSION_FORMATS
from .ledger import parse_major_minor, parse_version

UNCHANGED_FALLBACK_VERSION = "0.0.0"


class TagLedger(Protocol):
    def latest_version(self, prefix: str) -> str | None: ...

    def latest_version_in_line(self, prefix: str, major_minor: str) -> str | None: ...

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
        prefix = f"{package.name}-v"
        last_version = ledger.latest_version(prefix)
        last_in_line = ledger.latest_version_in_line(prefix, package.major_minor)
        changed = ledger.has_changes_since(f"{prefix}{last_version}" if last_version else None, package.path)
        if any(plans[dependency].publish for dependency in package.depends_on):
            changed = True
        plans[package.name] = PackagePlan(
            name=package.name,
            publish=changed,
            version=(
                next_version(package.major_minor, last_in_line, last_version, package.name)
                if changed
                else (last_version or UNCHANGED_FALLBACK_VERSION)
            ),
            last_version=last_version,
        )
    return plans


def next_version(major_minor: str, last_in_line: str | None, last_overall: str | None, subject: str) -> str:
    line = parse_major_minor(major_minor)
    if last_overall is not None and parse_version(last_overall)[:2] > line:
        raise ValueError(
            f"{subject}: declared major.minor {major_minor} is below ledger version {last_overall}; "
            "bump major_minor in publish-config.json"
        )
    if last_in_line is None:
        return f"{line[0]}.{line[1]}.0"
    major, minor, patch = parse_version(last_in_line)
    return f"{major}.{minor}.{patch + 1}"


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
            f"{registry_name}: {identity} @ {DEV_VERSION_FORMATS[registry_name](plan.version, run_id)}"
            for registry_name, identity in package.registries.items()
        )
        lines.append(f"| {plan.name} | True | {versions} |")
    return "\n".join(lines)
