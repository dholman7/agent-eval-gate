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
from contextlib import ExitStack, contextmanager
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
def _process(repo: Path, spec: AppSpec, values: dict[str, str], name: str) -> Iterator[None]:
    with tempfile.TemporaryDirectory(prefix=f"aeg-{name}-") as data_dir:
        filled = {**values, "data_dir": data_dir}
        env = {**os.environ, **{k: v.format(**filled) for k, v in spec.env.items()}}
        log = Path(data_dir) / f"{name}.log"
        with log.open("w") as out:
            process = subprocess.Popen(
                spec.command.format(**filled),
                shell=True,
                cwd=repo / spec.cwd,
                env=env,
                stdout=out,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            try:
                deadline = time.monotonic() + spec.timeout_s
                health = spec.health.format(**filled)
                while not _healthy(health):
                    if process.poll() is not None or time.monotonic() > deadline:
                        raise AppStartError(
                            f"{name} did not become healthy:\n{log.read_text()[-2000:]}"
                        )
                    time.sleep(0.2)
                yield
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)


@contextmanager
def running_app(repo: Path, spec: AppSpec, timeout_s: float | None = None) -> Iterator[int]:
    """Yields the port once the health check passes; kills the process group on exit."""
    if timeout_s is not None:
        spec = spec.model_copy(update={"timeout_s": timeout_s})
    port = free_port()
    with _process(repo, spec, {"port": str(port), "web_port": ""}, "app"):
        yield port


@contextmanager
def running_services(repo: Path, app: AppSpec, web: AppSpec | None) -> Iterator[dict[str, str]]:
    """The API, then the web app if given, each on a free port. Yields the template values
    (`port`, `web_port`) for the test command's environment."""
    values = {"port": str(free_port()), "web_port": str(free_port()) if web else ""}
    with ExitStack() as stack:
        stack.enter_context(_process(repo, app, values, "app"))
        if web is not None:
            stack.enter_context(_process(repo, web, values, "web"))
        yield values
