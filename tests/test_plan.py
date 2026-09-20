from pathlib import Path

from pubpkg import PackageConfig, compute_plan, next_version, render_summary, resolved_dependency_versions
from pubpkg.plan import TagLedger


class FakeLedger:
    def __init__(self, latest: dict[str, str], changed: dict[str, bool]) -> None:
        self.latest = latest
        self.changed = changed

    def latest_version(self, prefix: str) -> str | None:
        return self.latest.get(prefix)

    def has_changes_since(self, tag: str | None, path: Path) -> bool:
        return self.changed.get(path.as_posix(), False)


API_CLIENT = PackageConfig(
    name="placeframe-api-client", path=Path("packages/generated/csharp/api-client"), feeds={"nuget": "X"}
)
CORE = PackageConfig(name="placeframe-core", path=Path("packages/unity/Core"), feeds={"npm": "Y"})
ARFOUNDATION = PackageConfig(
    name="placeframe-arfoundation",
    path=Path("packages/unity/ARFoundation"),
    feeds={"npm": "Z"},
    depends_on=["placeframe-core"],
    dependency_pins={"org.outernet.placeframe": "placeframe-core"},
)
PACKAGES = [API_CLIENT, CORE, ARFOUNDATION]


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


def test_fake_ledger_satisfies_protocol():
    ledger: TagLedger = FakeLedger(latest={}, changed={})
    assert ledger.latest_version("x-v") is None
