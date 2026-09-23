from pathlib import Path

import pytest

from release_devkit.config import PackageConfig
from release_devkit.ledger import GitLedger
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


def preview_and_stable_tags(_prefix: str) -> list[str]:
    return ["1.0.6-preview", "1.0.5", "0.1.0-dev.1234", "0.1.0", "v1.0.5"]


def prerelease_only_tags(_prefix: str) -> list[str]:
    return ["1.0.6-preview", "0.1.0-dev.1234"]


class FakeLedger:
    def __init__(self, latest: dict[str, str], changed: dict[str, bool]) -> None:
        self.latest = latest
        self.changed = changed

    def latest_version(self, prefix: str) -> str | None:
        return self.latest.get(prefix)

    def has_changes_since(self, tag: str | None, path: Path) -> bool:
        return self.changed.get(path.as_posix(), False)


API_CLIENT = PackageConfig(
    name="placeframe-api-client", path=Path("packages/generated/csharp/api-client"), feeds={"nuget": "X", "npm": "N"}
)
CORE = PackageConfig(name="placeframe-core", path=Path("packages/unity/Core"), feeds={"npm": "Y"})
ARFOUNDATION = PackageConfig(
    name="placeframe-arfoundation",
    path=Path("packages/unity/ARFoundation"),
    feeds={"npm": "Z"},
    depends_on=["placeframe-core"],
    dependency_pins={"org.outernet.placeframe": "placeframe-core"},
)
COMMON = PackageConfig(name="placeframe-common", path=Path("packages/python/common"), feeds={"pypi": "P"})
PACKAGES = [API_CLIENT, CORE, ARFOUNDATION, COMMON]


def test_next_version_first_and_bump():
    assert next_version(None) == "0.1.0"
    assert next_version("0.1.7") == "0.1.8"
    assert next_version("1.9.10") == "1.9.11"


def test_plan_first_publish():
    ledger = FakeLedger(latest={}, changed={"packages/generated/csharp/api-client": True})

    plans = compute_plan([API_CLIENT], ledger)

    assert plans["placeframe-api-client"].publish is True
    assert plans["placeframe-api-client"].version == "0.1.0"


def test_plan_unchanged_package_carries_last_version():
    ledger = FakeLedger(
        latest={"placeframe-api-client-v": "0.1.7"},
        changed={"packages/generated/csharp/api-client": False},
    )

    plans = compute_plan([API_CLIENT], ledger)

    assert plans["placeframe-api-client"].publish is False
    assert plans["placeframe-api-client"].version == "0.1.7"


def test_plan_changed_package_patch_bumps():
    ledger = FakeLedger(
        latest={"placeframe-api-client-v": "0.1.7"},
        changed={"packages/generated/csharp/api-client": True},
    )

    plans = compute_plan([API_CLIENT], ledger)

    assert plans["placeframe-api-client"].publish is True
    assert plans["placeframe-api-client"].version == "0.1.8"


def test_plan_dependency_cascade_publishes_dependent():
    ledger = FakeLedger(
        latest={"placeframe-core-v": "0.2.0"},
        changed={
            "packages/unity/Core": True,
            "packages/unity/ARFoundation": False,
        },
    )

    plans = compute_plan(PACKAGES, ledger)

    assert plans["placeframe-core"].publish is True
    assert plans["placeframe-core"].version == "0.2.1"
    assert plans["placeframe-arfoundation"].publish is True
    assert plans["placeframe-arfoundation"].version == "0.1.0"


def test_resolved_dependency_versions_only_when_dependency_publishes():
    ledger = FakeLedger(
        latest={"placeframe-core-v": "0.2.0"},
        changed={
            "packages/unity/Core": False,
            "packages/unity/ARFoundation": True,
        },
    )
    plans = compute_plan(PACKAGES, ledger)

    assert plans["placeframe-arfoundation"].publish is True
    assert resolved_dependency_versions(ARFOUNDATION, plans) == {}

    cascade_ledger = FakeLedger(
        latest={"placeframe-core-v": "0.2.0"},
        changed={
            "packages/unity/Core": True,
            "packages/unity/ARFoundation": True,
        },
    )
    cascade_plans = compute_plan(PACKAGES, cascade_ledger)
    assert resolved_dependency_versions(ARFOUNDATION, cascade_plans) == {"org.outernet.placeframe": "0.2.1"}


def test_render_summary_lists_every_package():
    ledger = FakeLedger(
        latest={"placeframe-core-v": "0.2.0"},
        changed={
            "packages/generated/csharp/api-client": True,
            "packages/unity/Core": False,
            "packages/unity/ARFoundation": False,
        },
    )
    plans = compute_plan(PACKAGES, ledger)

    summary = render_summary(plans)

    assert "| placeframe-api-client | True | 0.1.0 |" in summary
    assert "| placeframe-core | False | 0.2.0 |" in summary
    assert "| placeframe-arfoundation | False | 0.0.0 |" in summary


def test_render_dev_summary_lists_per_feed_versions():
    ledger = FakeLedger(
        latest={},
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
    ledger: TagLedger = FakeLedger(latest={}, changed={})
    assert ledger.latest_version("x-v") is None
