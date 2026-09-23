from __future__ import annotations

from pathlib import Path


def append_line(path: str | None, text: str) -> None:
    if path:
        with Path(path).open("a", encoding="utf-8") as file:
            file.write(text + "\n")
