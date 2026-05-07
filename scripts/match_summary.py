"""対戦結果の集計・整形(plan C2)。

selfplay_match.py が出力した games.jsonl(または summary.json)を読み、
勝率・95%CI・Elo差を整形して標準出力に表示する。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from utils.elo import MatchStats, format_summary  # noqa: E402


def _load_games(path: Path) -> list[dict]:
    out = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out


def _stats_from_games(games: list[dict]) -> MatchStats:
    wins_a = sum(1 for g in games if g["result"] == "a_win")
    wins_b = sum(1 for g in games if g["result"] == "b_win")
    draws = sum(1 for g in games if g["result"] in ("draw", "max_ply"))
    iot = sum(1 for g in games if g["result"].startswith(("illegal_", "timeout_")))
    return MatchStats(
        games=len(games),
        wins_a=wins_a,
        losses_a=wins_b,
        draws=draws,
        illegal_or_timeout=iot,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="対戦結果の集計")
    ap.add_argument("--dir", help="selfplay_match.py の出力ディレクトリ(timestamp 付き)")
    ap.add_argument("--jsonl", help="games.jsonl のパス(--dir と択一)")
    args = ap.parse_args()

    if not args.dir and not args.jsonl:
        ap.error("--dir または --jsonl を指定してください")

    if args.dir:
        d = Path(args.dir).resolve()
        games_path = d / "games.jsonl"
        name_hint = d.name
    else:
        games_path = Path(args.jsonl).resolve()
        name_hint = games_path.parent.name

    if not games_path.exists():
        print(f"ERROR: {games_path} が見つかりません", file=sys.stderr)
        return 2

    games = _load_games(games_path)
    if not games:
        print("(まだ局がありません)")
        return 0

    stats = _stats_from_games(games)
    name = games[0].get("engine_a", "a") + "_vs_" + games[0].get("engine_b", "b") + " @ " + name_hint
    print(format_summary(name, stats))
    return 0


if __name__ == "__main__":
    sys.exit(main())
