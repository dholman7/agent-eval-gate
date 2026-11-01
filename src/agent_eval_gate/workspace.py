"""A checkout of the target repo at the benchmark's pinned ref, with dependencies installed."""

import difflib
import logging
import shutil
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from agent_eval_gate.benchmark import Bug, Target

logger = logging.getLogger(__name__)

# Large, regenerable directories are cloned into agent copies (copy-on-write, so instant and
# without duplicating disk), or symlinked where the filesystem can't clone. Next.js's Turbopack
# refuses a symlinked node_modules outside the project, so UI agents need the clone.
_SHARED = ("node_modules",)
# Never shared: `uv run` in a copy would re-point the base venv's editable install at the copy,
# so parallel trials would run each other's code and the base would end up pointing at a deleted
# directory. Left out, each copy gets its own venv from uv's cache on first use.
_PER_COPY = (".venv",)


def _sh(command: str, cwd: Path) -> None:
    subprocess.run(command, shell=True, cwd=cwd, check=True)


class Workspace:
    def __init__(self, path: Path) -> None:
        # Absolute, so symlinks made into agent copies resolve from any directory.
        self.path = path.resolve()

    @classmethod
    def prepare(cls, target: Target, cache_dir: Path, source: str | None = None) -> "Workspace":
        """Clones `source` (default: the target repo) at the pinned ref once per cache dir."""
        path = cache_dir / f"base-{target.ref[:12]}"
        marker = path / ".aeg-ready"
        if not marker.exists():
            shutil.rmtree(path, ignore_errors=True)
            path.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "clone", "--quiet", source or target.repo, str(path)], check=True
            )
            subprocess.run(["git", "-C", str(path), "checkout", "--quiet", target.ref], check=True)
            for command in target.setup:
                logger.info("setup: %s", command)
                _sh(command, path)
            marker.touch()
        return cls(path)

    def copy_for_agent(self, destination: Path) -> Path:
        """An isolated copy the agent may modify; scoring always uses the pristine base."""
        shutil.copytree(
            self.path,
            destination,
            symlinks=True,
            ignore=shutil.ignore_patterns(
                *_SHARED, *_PER_COPY, ".git", ".aeg-ready", "test-results", ".next"
            ),
        )
        for name in _SHARED:
            for heavy in [*self.path.glob(name), *self.path.glob(f"*/{name}")]:
                link = destination / heavy.relative_to(self.path)
                missing = link.parent.exists() and not link.is_symlink() and not link.exists()
                if missing and not _clone(heavy.resolve(), link):
                    link.symlink_to(heavy.resolve(), target_is_directory=True)
        return destination

    @contextmanager
    def mutated(self, bug: Bug) -> Iterator[None]:
        """Applies a seeded bug for the duration of the block, then restores the file exactly."""
        file = self.path / bug.file
        original = file.read_text()
        count = original.count(bug.old)
        if count != 1:
            raise ValueError(f"bug {bug.id}: expected 1 match in {bug.file}, found {count}")
        file.write_text(original.replace(bug.old, bug.new))
        try:
            yield
        finally:
            file.write_text(original)

    @contextmanager
    def with_support(self, files: dict[str, str], allowed: list[str]) -> Iterator[list[str]]:
        """Applies an agent's extensions to shared test files for the duration of the block.

        Only files in `allowed` are applied, and only when every existing line is kept: other
        tests depend on them. Yields why each other file was rejected; restores exactly.
        """
        rejected: list[str] = []
        originals: dict[Path, str] = {}
        for relative, content in files.items():
            target = self.path / relative
            if relative not in allowed:
                rejected.append(f"{relative}: not a file agents may extend")
            elif not target.is_file():
                rejected.append(f"{relative}: doesn't exist in the target")
            elif problem := _removed_lines(target.read_text(), content):
                rejected.append(f"{relative}: {problem}")
            else:
                originals[target] = target.read_text()
                target.write_text(content)
        try:
            yield rejected
        finally:
            for target, original in originals.items():
                target.write_text(original)

    @contextmanager
    def with_tests(self, relative_dir: str, files: dict[str, str]) -> Iterator[Path]:
        """Writes test files into the repo for the duration of the block."""
        directory = self.path / relative_dir
        shutil.rmtree(directory, ignore_errors=True)
        directory.mkdir(parents=True)
        for name, content in files.items():
            target = (directory / name).resolve()
            if not target.is_relative_to(directory.resolve()):
                raise ValueError(f"test file escapes the test directory: {name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        try:
            yield directory
        finally:
            shutil.rmtree(directory, ignore_errors=True)


def _clone(source: Path, destination: Path) -> bool:
    """Copy-on-write clone (APFS clonefile, or a reflink on Linux); False if unsupported."""
    flags = ["-cR"] if sys.platform == "darwin" else ["-a", "--reflink=always"]
    result = subprocess.run(["cp", *flags, str(source), str(destination)], capture_output=True)
    if result.returncode != 0:
        shutil.rmtree(destination, ignore_errors=True)
        return False
    return True


def _removed_lines(before: str, after: str) -> str | None:
    old, new = before.splitlines(), after.splitlines()
    for tag, i1, i2, _, _ in difflib.SequenceMatcher(a=old, b=new, autojunk=False).get_opcodes():
        if tag in ("delete", "replace"):
            return f"changes or removes existing lines {i1 + 1}-{i2}; only additions are allowed"
    return None
