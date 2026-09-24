from pathlib import Path

import pytest

from release_devkit.config import PackageConfig
from release_devkit.ledger import GitLedger, parse_major_minor, parse_version
from release_devkit.plan import (
    TagLedger,
    compute_plan,
    next_version,
    render_dev_summary,
    render_summary,
    resolved_dependency_versions,
)


def test_latest_version_skips_prerelease_tags(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "release_devkit.ledger.list_tag_versions",
        preview_and_stable_tags,
    )

    assert GitLedger().latest_version("pkg-v") == "1.0.5"


def test_latest_version_returns_none_when_no_stable_tag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "release_devkit.ledger.list_tag_versions",
        prerelease_only_tags,
    )

    assert GitLedger().latest_version("pkg-v") is None


def test_latest_version_in_line_filters_to_declared_line(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "release_devkit.ledger.list_tag_versions",
        multi_line_tags,
    )

    ledger = GitLedger()
    assert ledger.latest_version_in_line("pkg-v", "1.0") == "1.0.10"
    assert ledger.latest_version_in_line("pkg-v", "1.9") == "1.9.2"
    assert ledger.latest_version_in_line("pkg-v", "2.4") == "2.4.1"
    assert ledger.latest_version_in_line("pkg-v", "1.10") == "1.10.3"
    assert ledger.latest_version_in_line("pkg-v", "0.1") is None


def preview_and_stable_tags(_prefix: str) -> list[str]:
    return ["1.0.6-preview", "1.0.5", "0.1.0-dev.1234", "0.1.0", "v1.0.5"]


def prerelease_only_tags(_prefix: str) -> list[str]:
    return ["1.0.6-preview", "0.1.0-dev.1234"]


def multi_line_tags(_prefix: str) -> list[str]:
    return ["2.4.1", "2.4.0", "1.10.3", "1.9.2", "1.0.10", "1.0.9", "1.0.10-dev.5", "v1.0.9"]


class FakeLedger:
    def __init__(self, versions: dict[str, list[str]], changed: dict[str, bool]) -> None:
        self.versions = versions
        self.changed = changed

    def latest_version(self, prefix: str) -> str | None:
        versions = self.versions.get(prefix, [])
        return max(versions, key=parse_version) if versions else None

    def latest_version_in_line(self, prefix: str, major_minor: str) -> str | None:
        line = parse_major_minor(major_minor)
        in_line = [version for version in self.versions.get(prefix, []) if parse_version(version)[:2] == line]
        return max(in_line, key=parse_version) if in_line else None

    def has_changes_since(self, tag: str | None, path: Path) -> bool:
        return self.changed.get(path.as_posix(), False)


API_CLIENT = PackageConfig(
    name="placeframe-api-client",
    path=Path("packages/generated/csharp/api-client"),
    major_minor="0.1",
    feeds={"nuget": "X", "npm": "N"},
)
CORE = PackageConfig(name="placeframe-core", path=Path("packages/unity/Core"), major_minor="1.0", feeds={"npm": "Y"})
ARFOUNDATION = PackageConfig(
    name="placeframe-arfoundation",
    path=Path("packages/unity/ARFoundation"),
    major_minor="1.0",
    feeds={"npm": "Z"},
    depends_on=["placeframe-core"],
    dependency_pins={"org.outernet.placeframe": "placeframe-core"},
)
COMMON = PackageConfig(
    name="placeframe-common", path=Path("packages/python/common"), major_minor="0.1", feeds={"pypi": "P"}
)
PACKAGES = [API_CLIENT, CORE, ARFOUNDATION, COMMON]


def test_next_version_first_in_line_and_patch_bump():
    assert next_version("1.0", None, None, "pkg") == "1.0.0"
    assert next_version("0.1", "0.1.7", "0.1.7", "pkg") == "0.1.8"
    assert next_version("1.9", "1.9.10", "1.9.10", "pkg") == "1.9.11"


def test_next_version_new_line_above_old_ledger():
    assert next_version("1.4", None, "1.0.9", "pkg") == "1.4.0"
    assert next_version("2.0", None, "1.9.3", "pkg") == "2.0.0"


def test_next_version_app_derivation():
    assert next_version("1.0", None, None, "capture-tool") == "1.0.0"
    assert next_version("1.0", "1.0.0", "1.0.0", "capture-tool") == "1.0.1"


def test_next_version_guard_rejects_line_below_ledger():
    with pytest.raises(ValueError, match=r"below ledger version 1\.5\.2"):
        next_version("1.0", None, "1.5.2", "pkg")
    with pytest.raises(ValueError, match=r"below ledger version 1\.0\.0"):
        next_version("0.9", None, "1.0.0", "pkg")


def test_plan_first_publish_uses_declared_line():
    ledger = FakeLedger(
        versions={},
        changed={"packages/generated/csharp/api-client": True, "packages/unity/Core": True},
    )

    plans = compute_plan([API_CLIENT, CORE], ledger)

    assert plans["placeframe-api-client"].publish is True
    assert plans["placeframe-api-client"].version == "0.1.0"
    assert plans["placeframe-core"].publish is True
    assert plans["placeframe-core"].version == "1.0.0"


def test_plan_unchanged_package_carries_last_version():
    ledger = FakeLedger(
        versions={"placeframe-api-client-v": ["0.1.7"]},
        changed={"packages/generated/csharp/api-client": False},
    )

    plans = compute_plan([API_CLIENT], ledger)

    assert plans["placeframe-api-client"].publish is False
    assert plans["placeframe-api-client"].version == "0.1.7"


def test_plan_changed_package_patch_bumps_within_line():
    ledger = FakeLedger(
        versions={"placeframe-api-client-v": ["0.1.7"]},
        changed={"packages/generated/csharp/api-client": True},
    )

    plans = compute_plan([API_CLIENT], ledger)

    assert plans["placeframe-api-client"].publish is True
    assert plans["placeframe-api-client"].version == "0.1.8"


def test_plan_line_bump_publishes_first_version_of_new_line():
    ledger = FakeLedger(
        versions={"placeframe-api-client-v": ["1.0.9"]},
        changed={"packages/generated/csharp/api-client": True},
    )

    plans = compute_plan([API_CLIENT.model_copy(update={"major_minor": "1.4"})], ledger)

    assert plans["placeframe-api-client"].publish is True
    assert plans["placeframe-api-client"].version == "1.4.0"


def test_plan_guard_errors_when_line_is_below_ledger():
    ledger = FakeLedger(
        versions={"placeframe-api-client-v": ["1.5.2"]},
        changed={"packages/generated/csharp/api-client": True},
    )

    with pytest.raises(ValueError, match=r"placeframe-api-client: declared major\.minor 1\.4 is below ledger"):
        compute_plan([API_CLIENT.model_copy(update={"major_minor": "1.4"})], ledger)


def test_plan_dependency_cascade_publishes_dependent():
    ledger = FakeLedger(
        versions={"placeframe-core-v": ["1.0.5"]},
        changed={
            "packages/unity/Core": True,
            "packages/unity/ARFoundation": False,
        },
    )

    plans = compute_plan(PACKAGES, ledger)

    assert plans["placeframe-core"].publish is True
    assert plans["placeframe-core"].version == "1.0.6"
    assert plans["placeframe-arfoundation"].publish is True
    assert plans["placeframe-arfoundation"].version == "1.0.0"


def test_resolved_dependency_versions_only_when_dependency_publishes():
    ledger = FakeLedger(
        versions={"placeframe-core-v": ["1.0.5"]},
        changed={
            "packages/unity/Core": False,
            "packages/unity/ARFoundation": True,
        },
    )
    plans = compute_plan(PACKAGES, ledger)

    assert plans["placeframe-arfoundation"].publish is True
    assert resolved_dependency_versions(ARFOUNDATION, plans) == {}

    cascade_ledger = FakeLedger(
        versions={"placeframe-core-v": ["1.0.5"]},
        changed={
            "packages/unity/Core": True,
            "packages/unity/ARFoundation": True,
        },
    )
    cascade_plans = compute_plan(PACKAGES, cascade_ledger)
    assert resolved_dependency_versions(ARFOUNDATION, cascade_plans) == {"org.outernet.placeframe": "1.0.6"}


def test_render_summary_lists_every_package():
    ledger = FakeLedger(
        versions={"placeframe-core-v": ["1.0.5"]},
        changed={
            "packages/generated/csharp/api-client": True,
            "packages/unity/Core": False,
            "packages/unity/ARFoundation": False,
        },
    )
    plans = compute_plan(PACKAGES, ledger)

    summary = render_summary(plans)

    assert "| placeframe-api-client | True | 0.1.0 |" in summary
    assert "| placeframe-core | False | 1.0.5 |" in summary
    assert "| placeframe-arfoundation | False | 0.0.0 |" in summary


def test_render_dev_summary_lists_per_feed_versions():
    ledger = FakeLedger(
        versions={},
        changed={
            "packages/generated/csharp/api-client": True,
            "packages/unity/Core": False,
            "packages/unity/ARFoundation": False,
            "packages/python/common": True,
        },
    )
    plans = compute_plan(PACKAGES, ledger)

    summary = render_dev_summary(PACKAGES, plans, "4242")

    assert "| placeframe-api-client | True | nuget: X @ 0.1.0-dev.4242, npm: N @ 0.1.0-dev.4242 |" in summary
    assert "| placeframe-common | True | pypi: P @ 0.1.0.dev4242 |" in summary
    assert "| placeframe-core | False | - |" in summary


def test_fake_ledger_satisfies_protocol():
    ledger: TagLedger = FakeLedger(versions={}, changed={})
    assert ledger.latest_version("x-v") is None
