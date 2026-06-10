#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["typer"]
# ///
"""Publish the liatris tool as a standalone public git repo.

Clones origin into a temp dir, rewrites history with `git-filter-repo` so only
the liatris app remains, then prints the push command. Nothing is pushed unless
you pass --push.

liatris is a self-contained Electron app (its own package.json + pnpm-lock,
no workspace-package deps), so the keep set is just the app directory plus this
publish script.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import typer

# Workspace paths relevant to liatris to keep
KEEP_PATHS = [
    "apps/personal/tools/liatris/",
    "scripts/publish/publish-liatris.py",
]
# Paths purged from published history: tracked build artifacts
DROP_PATHS = [
    "apps/personal/tools/liatris/dist-electron/",
]
# README copied to the root so it renders on the frontpage
README_SRC = "apps/personal/tools/liatris/README.md"
# LICENSE copied to the root so the public repo is properly licensed.
# liatris has no LICENSE of its own; reuse the website's MIT license.
LICENSE_SRC = "apps/personal/website/LICENSE"
TARGET_URL = "https://github.com/ryangreenup/liatris.git"

app = typer.Typer(add_completion=False, help=__doc__)


def run(cmd: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run a command, echoing first, raising on non-zero exit."""
    typer.secho("  $ " + " ".join(cmd), fg=typer.colors.BRIGHT_BLACK)
    return subprocess.run(cmd, cwd=cwd, check=True, text=True, capture_output=True)


def copy_to_root(
    repo_root: Path, clone_dir: Path, src_rel: str, dest_name: str, commit_msg: str
) -> None:
    """Copy a working-tree file into the published repo root and commit it.

    Sourced from the local working tree (need not be committed) so it renders
    on the GitHub front page. Skips with a warning if the source is missing.
    """
    top_level = Path(
        run(["git", "rev-parse", "--show-toplevel"], cwd=repo_root).stdout.strip()
    )
    src = top_level / src_rel
    if not src.exists():
        typer.secho(
            f"warning: {src_rel} not found; skipping {dest_name} copy",
            err=True,
            fg=typer.colors.YELLOW,
        )
        return
    typer.echo(f"==> copying {dest_name} to repo root")
    shutil.copy2(src, clone_dir / dest_name)
    run(["git", "add", dest_name], cwd=clone_dir)
    run(["git", "commit", "-m", commit_msg], cwd=clone_dir)


@app.command()
def publish(
    push: bool = typer.Option(
        False, "--push", help="Push to the public repo (after confirmation)."
    ),
    force: bool = typer.Option(
        False, "--force", help="Force-push (overwrites public history). Implies --push."
    ),
) -> None:
    """Prepare (and optionally push) the standalone liatris repository."""
    if shutil.which("git-filter-repo") is None:
        typer.secho(
            "error: git-filter-repo not found (pipx install git-filter-repo)",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)

    repo_root = Path(__file__).resolve().parent
    origin = run(["git", "remote", "get-url", "origin"], cwd=repo_root).stdout.strip()
    clone_dir = Path(tempfile.mkdtemp(prefix="liatris-publish-"))
    push = push or force

    typer.echo(f"==> cloning {origin} -> {clone_dir}")
    run(["git", "clone", "--no-local", origin, str(clone_dir)])

    typer.echo("==> filtering history")
    run(
        ["git-filter-repo", *sum((["--path", p] for p in KEEP_PATHS), [])],
        cwd=clone_dir,
    )
    run(
        [
            "git-filter-repo",
            "--force",
            "--invert-paths",
            *sum((["--path", p] for p in DROP_PATHS), []),
        ],
        cwd=clone_dir,
    )

    copy_to_root(repo_root, clone_dir, LICENSE_SRC, "LICENSE", "chore: add LICENSE")
    copy_to_root(repo_root, clone_dir, README_SRC, "README.md", "docs: add README")

    files = run(["git", "ls-files"], cwd=clone_dir).stdout.split()
    if not files:
        typer.secho(
            "error: filtered repo is empty - check KEEP_PATHS",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)
    typer.echo(
        f"==> {len(files)} tracked files; top-level: {', '.join(sorted({f.split('/', 1)[0] for f in files}))}"
    )

    if not push:
        flag = "--force " if force else ""
        typer.echo(
            f"\n==> prepared (nothing pushed). To publish:\n"
            f"      cd {clone_dir}\n"
            f"      git remote add public {TARGET_URL}\n"
            f"      git push {flag}public HEAD:main"
        )
        return

    if force:
        typer.secho(
            "==> THIS WILL FORCE-OVERWRITE the public repo history.",
            err=True,
            fg=typer.colors.RED,
        )
    if not typer.confirm(
        f"Push to PUBLIC repo {TARGET_URL} (branch main)?", default=False
    ):
        typer.echo("aborted; nothing pushed")
        return

    run(["git", "remote", "add", "public", TARGET_URL], cwd=clone_dir)
    run(
        ["git", "push", *(["--force"] if force else []), "public", "HEAD:main"],
        cwd=clone_dir,
    )
    typer.echo("==> published.")


if __name__ == "__main__":
    app()
