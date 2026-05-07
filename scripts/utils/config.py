"""YAML 設定ローダー。

- ファイルを開いて parse する
- 値が `$env:NAME` 形式なら環境変数で置換(なければ ValueError)
- パスは設定ファイルからの相対 or プロジェクト相対のどちらでも解釈できるよう、
  呼び出し側で `Path(config_path).parent / value` の形で解決する想定
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml


_ENV_PATTERN = re.compile(r"^\$env:([A-Za-z_][A-Za-z0-9_]*)$")


def _substitute_env(node: Any) -> Any:
    if isinstance(node, str):
        m = _ENV_PATTERN.match(node)
        if m:
            name = m.group(1)
            val = os.environ.get(name)
            if val is None:
                raise ValueError(f"環境変数 {name} が設定されていません(YAML 内 $env:{name})")
            return val
        return node
    if isinstance(node, list):
        return [_substitute_env(x) for x in node]
    if isinstance(node, dict):
        return {k: _substitute_env(v) for k, v in node.items()}
    return node


def load_config(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise ValueError(f"YAML のトップレベルは dict であること: {p}")
    return _substitute_env(raw)


def resolve_path(config_path: str | Path, value: str | None) -> Path | None:
    """設定 YAML 内のパス値(value)を、設定ファイルからの相対として解決する。

    None が来たら None を返す。絶対パスならそのまま。
    """
    if value is None:
        return None
    p = Path(value)
    if p.is_absolute():
        return p
    return (Path(config_path).resolve().parent / p).resolve()
