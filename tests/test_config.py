import json
from pathlib import Path

import pytest
from pydantic import ValidationError

import pubpkg
from pubpkg import load_config, select_packages


def write_config(tmp_path: Path, payload: dict[str, object]) -> Path:
    config_path = tmp_path / "publish-config.json"
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    return config_path


def base_payload() -> dict[str, object]:
    return {
        "packages": [
            {
                "name": "placeframe-api-client",
                "path": "packages/generated/csharp/api-client/src/PlaceframeApiClient",
                "feeds": {"nuget": "PlaceframeApiClient"},
            },
            {
                "name": "placeframe-core",
                "path": "packages/unity/Placeframe/Assets/Package/Core",
                "feeds": {"npm": "org.outernet.placeframe"},
            },
            {
                "name": "placeframe-arfoundation",
                "path": "packages/unity/Placeframe/Assets/Package/ARFoundation",
                "feeds": {"npm": "org.outernet.placeframe.arfoundation"},
                "depends_on": ["placeframe-core"],
                "dependency_pins": {"org.outernet.placeframe": "placeframe-core"},
            },
        ],
        "apps": [
            {
                "name": "CaptureTool",
                "path": "apps/CaptureTool",
                "tag_prefix": "capture-tool",
                "display_name": "Capture Tool",
            },
        ],
        "compose_files": ["compose.bake.yml"],
        "ci_workflow": "placeframe-ci.yml",
        "mirror_prefix": "ghcr.io/outernet-foundation/mirror",
    }


def payload_with_unknown_dependency() -> dict[str, object]:
    return {
        "packages": [
            {
                "name": "placeframe-api-client",
                "path": "packages/generated/csharp/api-client",
                "depends_on": ["nonexistent"],
            },
        ],
        "ci_workflow": "placeframe-ci.yml",
        "mirror_prefix": "ghcr.io/outernet-foundation/mirror",
    }


def payload_with_late_dependency() -> dict[str, object]:
    return {
        "packages": [
            {
                "name": "placeframe-arfoundation",
                "path": "packages/unity/ARFoundation",
                "depends_on": ["placeframe-core"],
            },
            {
                "name": "placeframe-core",
                "path": "packages/unity/Core",
            },
        ],
        "ci_workflow": "placeframe-ci.yml",
        "mirror_prefix": "ghcr.io/outernet-foundation/mirror",
    }


def payload_with_unknown_pin() -> dict[str, object]:
    return {
        "packages": [
            {
                "name": "placeframe-core",
                "path": "packages/unity/Core",
                "dependency_pins": {"org.example.foo": "nonexistent"},
            },
        ],
        "ci_workflow": "placeframe-ci.yml",
        "mirror_prefix": "ghcr.io/outernet-foundation/mirror",
    }


def test_load_config_parses_packages(tmp_path: Path):
    config = load_config(write_config(tmp_path, base_payload()))

    assert [p.name for p in config.packages] == [
        "placeframe-api-client",
        "placeframe-core",
        "placeframe-arfoundation",
    ]
    arfoundation = config.packages[2]
    assert arfoundation.depends_on == ["placeframe-core"]
    assert arfoundation.dependency_pins == {"org.outernet.placeframe": "placeframe-core"}
    assert config.apps[0].tag_prefix == "capture-tool"
    assert config.mirror_prefix == "ghcr.io/outernet-foundation/mirror"
    assert config.artifact_dir == Path("/tmp/release-artifacts")


def test_load_config_rejects_unknown_dependency(tmp_path: Path):
    with pytest.raises(ValidationError, match="unknown package 'nonexistent'"):
        load_config(write_config(tmp_path, payload_with_unknown_dependency()))


def test_load_config_rejects_dependencies_declared_later(tmp_path: Path):
    with pytest.raises(ValidationError, match="appears later in the list"):
        load_config(write_config(tmp_path, payload_with_late_dependency()))


def test_load_config_rejects_unknown_dependency_pin(tmp_path: Path):
    with pytest.raises(ValidationError, match="pins unknown package 'nonexistent'"):
        load_config(write_config(tmp_path, payload_with_unknown_pin()))


def package_names(packages: list[pubpkg.PackageConfig]) -> list[str]:
    return [package.name for package in packages]


def loaded_packages(tmp_path: Path) -> list[pubpkg.PackageConfig]:
    return load_config(write_config(tmp_path, base_payload())).packages


def test_select_packages_only_preserves_config_order(tmp_path: Path):
    packages = loaded_packages(tmp_path)

    selected = select_packages(packages, ["placeframe-arfoundation", "placeframe-api-client"], [])

    assert package_names(selected) == ["placeframe-api-client", "placeframe-arfoundation"]


def test_select_packages_exclude(tmp_path: Path):
    packages = loaded_packages(tmp_path)

    selected = select_packages(packages, [], ["placeframe-core"])

    assert package_names(selected) == ["placeframe-api-client", "placeframe-arfoundation"]


def test_select_packages_unfiltered_returns_all(tmp_path: Path):
    packages = loaded_packages(tmp_path)

    assert package_names(select_packages(packages, [], [])) == [
        "placeframe-api-client",
        "placeframe-core",
        "placeframe-arfoundation",
    ]


def test_select_packages_rejects_unknown_name(tmp_path: Path):
    packages = loaded_packages(tmp_path)

    with pytest.raises(SystemExit, match="Unknown package 'nope'"):
        select_packages(packages, ["nope"], [])


def test_select_packages_rejects_only_with_exclude(tmp_path: Path):
    packages = loaded_packages(tmp_path)

    with pytest.raises(SystemExit, match="mutually exclusive"):
        select_packages(packages, ["placeframe-core"], ["placeframe-core"])
