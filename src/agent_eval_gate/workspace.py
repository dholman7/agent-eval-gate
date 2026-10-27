"""A checkout of the target repo at the benchmark's pinned ref, with dependencies installed."""

import logging
import shutil
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from agent_eval_gate.benchmark import Bug, Target

logger = logging.getLogger(__name__)

# Large, regenerable directories are symlinked into agent copies instead of copied.
_HEAVY = ("node_modules", ".venv")


def _sh(command: str, cwd: Path) -> None:
    subprocess.run(command, shell=True, cwd=cwd, check=True)


class Workspace:
    def __init__(self, path: Path) -> None:
        self.path = path

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
            ignore=shutil.ignore_patterns(*_HEAVY, ".git", ".aeg-ready", "test-results"),
        )
        for name in _HEAVY:
            for heavy in [*self.path.glob(name), *self.path.glob(f"*/{name}")]:
                link = destination / heavy.relative_to(self.path)
                if link.parent.exists() and not link.exists():
                    link.symlink_to(heavy, target_is_directory=True)
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
