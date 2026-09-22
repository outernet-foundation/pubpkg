from __future__ import annotations

import typer
from bashrun.bash import bash_output

app = typer.Typer(add_completion=False, pretty_exceptions_show_locals=False)

BASE_BRANCH = "main"


@app.command()
def main() -> None:
    existing = bash_output(
        f'gh pr list --head dev --base {BASE_BRANCH} --state open --json number --jq ".[0].number"'
    ).strip()
    if existing:
        print(f"Release PR already exists: #{existing}")
    else:
        bash_output(
            f'gh pr create --head dev --base {BASE_BRANCH} --title "Next release"'
            ' --body "Persistent release gate PR from `dev` → `main`. Merge when ready to cut a release."'
        )
        print("Created release PR")
