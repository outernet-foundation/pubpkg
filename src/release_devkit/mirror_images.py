from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

import typer
from bashrun import bash
from docker_devkit.image_refs import collect_repo_references
from unity_devkit.ci_step import ci_step

from .config import load_config

app = typer.Typer(add_completion=False, pretty_exceptions_show_locals=False)

CRANE_VERSION = "v0.22.1"


@app.command()
def main(config: Annotated[Path, typer.Option(help="Publish configuration JSON")]) -> None:
    publish_config = load_config(config)
    mirror_prefix = publish_config.mirror_prefix
    targets = {
        occurrence.reference: occurrence.reference[len(mirror_prefix) + 1 :]
        for occurrence in collect_repo_references(Path.cwd(), dockerfile_glob=None)
        if occurrence.reference.startswith(f"{mirror_prefix}/")
    }
    with ci_step("Install crane"):
        sudo = "sudo " if os.geteuid() != 0 else ""
        archive = "go-containerregistry_Linux_x86_64.tar.gz"
        bash(f"curl -fsSLO https://github.com/google/go-containerregistry/releases/download/{CRANE_VERSION}/{archive}")
        bash(f"{sudo}tar -xzf {archive} -C /usr/local/bin crane")
        Path(archive).unlink()
    for mirrored, upstream in sorted(targets.items()):
        with ci_step(f"Mirror {upstream} -> {mirrored}"):
            bash(f"crane copy {upstream} {mirrored}")
    print(f"Mirrored images: {len(targets)}")
