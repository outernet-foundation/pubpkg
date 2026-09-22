import json
from pathlib import Path

import pytest

from release_devkit.feeds import NpmFeed, PublishRequest
from release_devkit.feeds import (
    DEV_VERSION_FORMATS,
    KNOWN_FEEDS,
    ephemeral_manifest_patch,
    ephemeral_pyproject_patch,
    patch_project_version,
    pep440_dev_version,
    semver_dev_version,
)

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


class CommandRecorder:
    def __init__(self) -> None:
        self.commands: list[str] = []

    def __call__(
        self,
        command: str,
        *,
        cwd: Path | None = None,
        stdin_text: str | None = None,
        env: dict[str, str] | None = None,
    ) -> str:
        self.commands.append(command)
        return ""


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


def test_dev_version_spellings_per_registry() -> None:
    assert semver_dev_version("0.1.8", "123456") == "0.1.8-dev.123456"
    assert pep440_dev_version("0.1.8", "123456") == "0.1.8.dev123456"


def test_dev_version_formats_cover_every_known_feed() -> None:
    assert set(DEV_VERSION_FORMATS) == KNOWN_FEEDS


def test_npm_publish_rides_the_dev_dist_tag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest_path = write_manifest(tmp_path)
    recorder = CommandRecorder()
    monkeypatch.setattr("release_devkit.feeds.bash_output", recorder)

    NpmFeed().publish(
        PublishRequest(
            path=tmp_path,
            identity="org.outernet.placeframe",
            version="0.2.1-dev.42",
            dependency_versions={},
            dist_tag="dev",
        )
    )

    assert recorder.commands == ["npm publish --access public --provenance --tag dev"]
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["version"] == "0.0.0-local"


def test_npm_publish_without_dist_tag_leaves_latest_alone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_manifest(tmp_path)
    recorder = CommandRecorder()
    monkeypatch.setattr("release_devkit.feeds.bash_output", recorder)

    NpmFeed().publish(
        PublishRequest(path=tmp_path, identity="org.outernet.placeframe", version="0.2.1", dependency_versions={})
    )

    assert recorder.commands == ["npm publish --access public --provenance"]
