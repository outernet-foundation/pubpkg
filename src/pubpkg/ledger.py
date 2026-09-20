import re
from pathlib import Path

from bashrun import bash, bash_check, bash_output

# Prerelease-suffixed tags (e.g. 1.0.6-preview) are not stable-ledger versions: the stable flow
# must never compute a next version from one. Dev-channel versions never enter the tag space.
STABLE_VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


def is_stable_version(version: str) -> bool:
    return STABLE_VERSION_PATTERN.fullmatch(version) is not None


class GitLedger:
    def latest_version(self, prefix: str) -> str | None:
        output = bash_output(f'git tag --list "{prefix}*" --sort=-v:refname').strip()
        if not output:
            return None
        for tag in output.splitlines():
            version = tag[len(prefix) :]
            if is_stable_version(version):
                return version
        return None

    def has_changes_since(self, tag: str | None, path: Path) -> bool:
        if tag is None:
            return True
        return not bash_check(f"git diff --quiet {tag} HEAD -- {path}")

    def create_and_push_tag(self, tag: str) -> None:
        bash(f"git tag {tag}")
        bash(f"git push origin {tag}")
