from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from .feeds import KNOWN_FEEDS


class PackageConfig(BaseModel):
    name: str
    path: Path
    feeds: dict[str, str] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    dependency_pins: dict[str, str] = Field(default_factory=dict)


class AppConfig(BaseModel):
    name: str
    path: Path
    tag_prefix: str
    display_name: str


class PublishConfig(BaseModel):
    packages: list[PackageConfig]
    apps: list[AppConfig] = Field(default_factory=list)
    compose_files: list[str] = Field(default_factory=list)
    ci_workflow: str
    mirror_prefix: str
    artifact_dir: Path = Path("/tmp/release-artifacts")
    artifact_skip_prefixes: list[str] = Field(default_factory=lambda: ["env-lock-", "versions"])
    artifact_skip_suffixes: list[str] = Field(default_factory=lambda: ["-build-report"])

    @model_validator(mode="after")
    def validate_dependency_graph(self) -> "PublishConfig":
        seen: set[str] = set()
        for package in self.packages:
            for dependency in package.depends_on:
                if dependency not in seen:
                    if dependency in {p.name for p in self.packages}:
                        message = f"package '{package.name}' depends on '{dependency}', which appears later in the list; packages must be ordered dependencies-first"
                    else:
                        message = f"package '{package.name}' depends on unknown package '{dependency}'"
                    raise ValueError(message)
            seen.add(package.name)

        names = {package.name for package in self.packages}
        for package in self.packages:
            for pinned in package.dependency_pins.values():
                if pinned not in names:
                    raise ValueError(f"package '{package.name}' pins unknown package '{pinned}'")

        return self

    @model_validator(mode="after")
    def validate_feed_names(self) -> "PublishConfig":
        for package in self.packages:
            unknown_feeds = set(package.feeds) - KNOWN_FEEDS
            if unknown_feeds:
                raise ValueError(f"package '{package.name}' declares unknown feeds: {sorted(unknown_feeds)}")
        return self


def load_config(path: Path) -> PublishConfig:
    return PublishConfig.model_validate_json(path.read_text(encoding="utf-8"))


def select_packages(packages: list[PackageConfig], only: Sequence[str], exclude: Sequence[str]) -> list[PackageConfig]:
    if only and exclude:
        raise SystemExit("--only and --exclude are mutually exclusive")
    names = [package.name for package in packages]
    for requested in [*only, *exclude]:
        if requested not in names:
            raise SystemExit(f"Unknown package '{requested}'. Valid: {', '.join(names)}")
    if only:
        selected = set(only)
        return [package for package in packages if package.name in selected]
    if exclude:
        deselected = set(exclude)
        return [package for package in packages if package.name not in deselected]
    return packages
