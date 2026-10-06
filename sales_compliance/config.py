"""Configuration loading."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

try:  # .env is optional; real deployments use a secrets manager
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:  # pragma: no cover
    pass


def load_config(path: str | Path | None = None) -> dict:
    """Load config.yaml (or the file named by SALES_COMPLIANCE_CONFIG)."""
    config_path = Path(path or os.environ.get("SALES_COMPLIANCE_CONFIG", ROOT / "config.yaml"))
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve(path: str | Path) -> Path:
    """Resolve a config path relative to the repo root."""
    p = Path(path)
    return p if p.is_absolute() else ROOT / p
