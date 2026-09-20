import json
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from subprocess import CalledProcessError
from typing import Protocol

from bashrun import bash, bash_output

NUGET_SOURCE = "https://api.nuget.org/v3/index.json"


@dataclass(frozen=True)
class PublishRequest:
    path: Path
    identity: str
    version: str
    dependency_versions: dict[str, str]


class Feed(Protocol):
    def publish(self, request: PublishRequest) -> None: ...


class NuGetFeed:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def publish(self, request: PublishRequest) -> None:
        bash(f"dotnet pack -c Release -p:Version={request.version} -o ./nupkg", cwd=request.path)
        bash(
            f"dotnet nuget push ./nupkg/*.nupkg --api-key {self.api_key} --source {NUGET_SOURCE} --skip-duplicate",
            cwd=request.path,
        )


class NpmFeed:
    def publish(self, request: PublishRequest) -> None:
        with ephemeral_manifest_patch(request.path, request.version, request.dependency_versions):
            try:
                bash_output("npm publish --access public --provenance", cwd=request.path)
            except CalledProcessError as e:
                stderr = e.stderr or ""
                if "EPUBLISHCONFLICT" in stderr or "cannot publish over existing version" in stderr:
                    print("  Version already published, skipping (idempotent)")
                else:
                    raise


@contextmanager
def ephemeral_manifest_patch(package_path: Path, version: str, dependency_versions: dict[str, str]) -> Generator[None]:
    manifest_path = package_path / "package.json"
    original = manifest_path.read_text(encoding="utf-8")
    try:
        manifest = json.loads(original)
        manifest["version"] = version
        for dependency_name, dependency_version in dependency_versions.items():
            manifest["dependencies"][dependency_name] = dependency_version
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        yield
    finally:
        manifest_path.write_text(original, encoding="utf-8")


def build_feeds(nuget_api_key: str) -> dict[str, Feed]:
    return {"nuget": NuGetFeed(nuget_api_key), "npm": NpmFeed()}
