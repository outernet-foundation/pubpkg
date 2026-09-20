from pathlib import Path

from bashrun import bash, bash_check, bash_output


class GitLedger:
    def latest_version(self, prefix: str) -> str | None:
        output = bash_output(f'git tag --list "{prefix}*" --sort=-v:refname').strip()
        if not output:
            return None
        return output.splitlines()[0][len(prefix) :]

    def has_changes_since(self, tag: str | None, path: Path) -> bool:
        if tag is None:
            return True
        return not bash_check(f"git diff --quiet {tag} HEAD -- {path}")

    def create_and_push_tag(self, tag: str) -> None:
        bash(f"git tag {tag}")
        bash(f"git push origin {tag}")
