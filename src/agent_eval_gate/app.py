"""Starts the system under test on a free port with a throwaway data directory."""

import os
import signal
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from agent_eval_gate.benchmark import AppSpec


class AppStartError(RuntimeError):
    pass


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
        return port


def _healthy(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=1) as response:  # noqa: S310 - local URL
            return bool(response.status == 200)
    except (urllib.error.URLError, ConnectionError, TimeoutError):
        return False


@contextmanager
def running_app(repo: Path, spec: AppSpec, timeout_s: float = 60) -> Iterator[int]:
    """Yields the port once the health check passes; kills the process group on exit."""
    port = free_port()
    with tempfile.TemporaryDirectory(prefix="aeg-app-") as data_dir:
        values = {"port": str(port), "data_dir": data_dir}
        env = {**os.environ, **{k: v.format(**values) for k, v in spec.env.items()}}
        log = Path(data_dir) / "app.log"
        with log.open("w") as out:
            process = subprocess.Popen(
                spec.command.format(**values),
                shell=True,
                cwd=repo / spec.cwd,
                env=env,
                stdout=out,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            try:
                deadline = time.monotonic() + timeout_s
                health = spec.health.format(**values)
                while not _healthy(health):
                    if process.poll() is not None or time.monotonic() > deadline:
                        raise AppStartError(
                            f"app did not become healthy:\n{log.read_text()[-2000:]}"
                        )
                    time.sleep(0.2)
                yield port
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
