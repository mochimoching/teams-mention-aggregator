"""TOML configuration loader for Agent."""

import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]


def load_config(path: Path | None = None) -> dict:
    """Load config.toml and return as dict.

    Search order:
    1. Explicit path argument
    2. config.toml in current directory
    3. config.toml next to this script's parent directory
    """
    if path is None:
        candidates = [
            Path.cwd() / "config.toml",
            Path(__file__).resolve().parent.parent / "config.toml",
        ]
        for c in candidates:
            if c.exists():
                path = c
                break
        else:
            raise FileNotFoundError(
                "config.toml not found. Copy config.example.toml to config.toml and edit it."
            )

    with open(path, "rb") as f:
        return tomllib.load(f)
