from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class AppConfig:
    root: Path
    assets: dict[str, Any]
    strategy: dict[str, Any]
    budget: dict[str, Any]
    calendars: dict[str, Any]


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}")
    return data


def load_config(root: Path | None = None) -> AppConfig:
    project_root = root or Path.cwd()
    config_dir = project_root / "config"
    return AppConfig(
        root=project_root,
        assets=load_yaml(config_dir / "assets.yaml"),
        strategy=load_yaml(config_dir / "strategy.yaml"),
        budget=load_yaml(config_dir / "budget.yaml"),
        calendars=load_yaml(config_dir / "calendars.yaml"),
    )
