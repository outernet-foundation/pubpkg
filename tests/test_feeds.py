import json
from pathlib import Path

import pytest

from pubpkg.feeds import ephemeral_manifest_patch, ephemeral_pyproject_patch, patch_project_version

PYPROJECT = (
    "[project]\n"
    'name = "example"\n'
    'version = "0.0.0.dev0"\n'
    'dependencies = ["pydantic>=2"]\n'
    "\n"
    "[tool.hatch.version]\n"
    'version = "not-this-one"\n'
    "\n"
    "[build-system]\n"
    'requires = ["hatchling"]\n'
)


def write_manifest(tmp_path: Path) -> Path:
    manifest_path = tmp_path / "package.json"
    manifest_path.write_text(
        json.dumps({"name": "org.outernet.placeframe", "version": "0.0.0-local", "dependencies": {}}),
        encoding="utf-8",
    )
    return manifest_path


def test_patch_updates_version_and_pins_then_restores(tmp_path: Path):
    manifest_path = write_manifest(tmp_path)

    with ephemeral_manifest_patch(tmp_path, "0.2.1", {"org.outernet.placeframe.apiclient": "0.1.8"}):
        patched = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert patched["version"] == "0.2.1"
        assert patched["dependencies"] == {"org.outernet.placeframe.apiclient": "0.1.8"}

    restored = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert restored["version"] == "0.0.0-local"
    assert restored["dependencies"] == {}


def test_patch_restores_on_error(tmp_path: Path):
    manifest_path = write_manifest(tmp_path)
    original = manifest_path.read_text(encoding="utf-8")

    with pytest.raises(RuntimeError), ephemeral_manifest_patch(tmp_path, "0.2.1", {}):
        raise RuntimeError("publish exploded")

    assert manifest_path.read_text(encoding="utf-8") == original


def test_patch_project_version_replaces_the_project_table_version() -> None:
    patched = patch_project_version(PYPROJECT, "0.1.3")
    assert 'version = "0.1.3"\n' in patched
    assert 'version = "0.0.0.dev0"' not in patched
    assert 'version = "not-this-one"' in patched


def test_patch_project_version_raises_without_a_project_version() -> None:
    without_version = '[project]\nname = "example"\n\n[build-system]\nrequires = ["hatchling"]\n'
    with pytest.raises(ValueError, match="no \\[project\\] version"):
        patch_project_version(without_version, "0.1.3")


def test_ephemeral_pyproject_patch_restores_the_original(tmp_path: Path) -> None:
    manifest_path = tmp_path / "pyproject.toml"
    manifest_path.write_text(PYPROJECT, encoding="utf-8")

    with ephemeral_pyproject_patch(tmp_path, "0.2.0"):
        assert 'version = "0.2.0"' in manifest_path.read_text(encoding="utf-8")

    assert manifest_path.read_text(encoding="utf-8") == PYPROJECT


def test_ephemeral_pyproject_patch_restores_on_error(tmp_path: Path) -> None:
    manifest_path = tmp_path / "pyproject.toml"
    manifest_path.write_text(PYPROJECT, encoding="utf-8")

    with pytest.raises(RuntimeError), ephemeral_pyproject_patch(tmp_path, "0.2.0"):
        raise RuntimeError("publish exploded")

    assert manifest_path.read_text(encoding="utf-8") == PYPROJECT
