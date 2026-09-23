import re
from pathlib import Path

from ci_devkit.git_tags import (
    create_and_push_tag as push_tag,
    has_changes_since_tag,
    list_tag_versions,
)

# Prerelease-suffixed tags (e.g. 1.0.6-preview) are not stable-ledger versions: the stable flow
# must never compute a next version from one. Dev-channel versions never enter the tag space.
STABLE_VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


class GitLedger:
    def latest_version(self, prefix: str) -> str | None:
        for version in list_tag_versions(prefix):
            if is_stable_version(version):
                return version
        return None

    def has_changes_since(self, tag: str | None, path: Path) -> bool:
        return has_changes_since_tag(tag, path)

    def create_and_push_tag(self, tag: str) -> None:
        push_tag(tag)


def is_stable_version(version: str) -> bool:
    return STABLE_VERSION_PATTERN.fullmatch(version) is not None
