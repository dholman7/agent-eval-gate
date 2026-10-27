"""Pulls one scenario (with the feature header and Background) out of a .feature file."""

import re

_BLOCK_START = re.compile(r"^\s*(Scenario|Scenario Outline|Background|Rule):")


def scenario_text(feature: str, scenario: str) -> str:
    lines = feature.splitlines()
    header: list[str] = []
    background: list[str] = []
    found: list[str] = []
    current: list[str] | None = header
    for line in lines:
        match = _BLOCK_START.match(line)
        if match:
            name = line.split(":", 1)[1].strip()
            if match.group(1) == "Background":
                current = background
            elif name == scenario:
                current = found
            else:
                current = None
        if current is not None:
            current.append(line)
    if not found:
        raise KeyError(f"Scenario not found: {scenario!r}")
    parts = ["\n".join(header).rstrip(), "\n".join(background).rstrip(), "\n".join(found).rstrip()]
    return "\n\n".join(p for p in parts if p) + "\n"
