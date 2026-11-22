"""Locate curriculum data and the learner file.

The learner file lives outside the skill directory so updating the skill
does not wipe progress. Override with ``OTO_LEARNER`` or ``--learner``.
"""

from __future__ import annotations

import os
from pathlib import Path


def package_dir() -> Path:
    return Path(__file__).resolve().parent


def repo_root() -> Path | None:
    here = package_dir()
    for candidate in (here.parents[1], here.parents[2] if len(here.parents) > 2 else None):
        if candidate is None:
            continue
        if (candidate / "data" / "levels.yaml").is_file():
            return candidate
    return None


def data_dir() -> Path:
    env = os.environ.get("OTO_DATA")
    if env:
        path = Path(env).expanduser()
        if not path.is_dir():
            raise FileNotFoundError(f"OTO_DATA 不是目录：{path}")
        return path
    root = repo_root()
    if root is not None:
        return root / "data"
    bundled = package_dir() / "data"
    if (bundled / "levels.yaml").is_file():
        return bundled
    raise FileNotFoundError("找不到课程数据。请在仓库里运行，或设置 OTO_DATA。")


def skill_root() -> Path:
    root = repo_root()
    if root is not None:
        return root
    return package_dir()


def learner_path(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    env = os.environ.get("OTO_LEARNER")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".oto" / "learner.yaml"
