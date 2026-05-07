"""自己対戦実行スクリプト(plan C1)。

2 つの USIエンジン定義を YAML から読み、N 局自動対戦して結果を保存する。

使い方:
    python scripts/selfplay_match.py --config configs/match/baseline.yaml

出力:
    <output_dir>/<timestamp>/games.jsonl    各局の結果(1行=1局のJSON)
    <output_dir>/<timestamp>/summary.json   集計済みサマリ(scripts/match_summary.py が再利用)
    <output_dir>/<timestamp>/config.yaml    実行時設定のコピー
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import random
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

# cshogi は対局終局判定・合法手チェック用
try:
    import cshogi
    from cshogi import Board, BLACK, WHITE
except ImportError:  # pragma: no cover
    print(
        "ERROR: cshogi が見つかりません。`pip install -r requirements.txt` を実行してください。",
        file=sys.stderr,
    )
    raise

# ローカル utils は scripts/ ルート直下から import 可能にする
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from utils.config import load_config, resolve_path  # noqa: E402
from utils.elo import MatchStats, format_summary  # noqa: E402
from utils.usi import UsiEngine  # noqa: E402


# ============== データ型 ==============


@dataclass
class EngineDef:
    name: str
    binary: str
    options: dict


@dataclass
class GameResult:
    game_id: int
    engine_a: str
    engine_b: str
    a_color: str          # "black" or "white"
    moves: list[str]
    result: str           # "a_win" / "b_win" / "draw" / "illegal_a" / "illegal_b" / "timeout_a" / "timeout_b" / "max_ply"
    plies: int
    duration_sec: float
    sfen: str             # 最終局面


# ============== 1局の対戦実装 ==============


def _build_go_args(byoyomi_ms: int | None) -> str:
    # MVP: byoyomi のみ対応。その他の time control は段階的に拡張
    if byoyomi_ms is not None:
        return f"byoyomi {byoyomi_ms}"
    return "movetime 1000"


def _engine_def_from_dict(d: dict, config_path: Path) -> EngineDef:
    binary = resolve_path(config_path, d["binary"])
    options = dict(d.get("options") or {})
    # EvalDir のような相対パスを絶対化
    if "EvalDir" in options and options["EvalDir"]:
        ev = resolve_path(config_path, options["EvalDir"])
        options["EvalDir"] = str(ev)
    if "BookFile" in options and options["BookFile"]:
        bf = resolve_path(config_path, options["BookFile"])
        options["BookFile"] = str(bf)
    return EngineDef(name=d["name"], binary=str(binary), options=options)


def _start_engine(eng: EngineDef) -> UsiEngine:
    cwd = Path(eng.binary).parent
    e = UsiEngine(eng.binary, cwd=cwd)
    e.start()
    e.usi_handshake()
    e.setoptions(eng.options)
    e.isready()
    return e


def play_one_game(
    game_id: int,
    eng_black: EngineDef,
    eng_white: EngineDef,
    byoyomi_ms: int,
    max_ply: int = 320,
) -> GameResult:
    """指定された先後で1局指す。先後は呼び出し側で決める。"""
    t0 = time.monotonic()
    board = Board()
    moves: list[str] = []
    result = "draw"
    a_color = "black" if eng_black.name == "<engine_a>" else "white"  # 上書きされる
    # ただし呼び出し元で名前を <engine_a>/<engine_b> に置換しておく方式。後述で統一

    e_b = _start_engine(eng_black)
    e_w = _start_engine(eng_white)
    try:
        e_b.usinewgame()
        e_w.usinewgame()

        for ply in range(max_ply):
            engine = e_b if board.turn == BLACK else e_w
            try:
                engine.position("startpos", moves)
                bestmove, _ = engine.go_and_get_bestmove(
                    _build_go_args(byoyomi_ms),
                    timeout=max(byoyomi_ms / 1000.0 * 5 + 5, 15),  # byoyomiの5倍+5秒
                )
            except TimeoutError:
                # 思考時間切れ扱い
                result = "timeout_black" if board.turn == BLACK else "timeout_white"
                break

            if bestmove == "resign":
                result = "white_win" if board.turn == BLACK else "black_win"
                break
            if bestmove == "win":
                # 入玉宣言勝ち
                result = "black_win" if board.turn == BLACK else "white_win"
                break

            # 合法手チェック
            try:
                move = board.move_from_usi(bestmove)
            except Exception:
                result = "illegal_black" if board.turn == BLACK else "illegal_white"
                break
            if not board.is_legal(move):
                result = "illegal_black" if board.turn == BLACK else "illegal_white"
                break

            board.push(move)
            moves.append(bestmove)

            if board.is_game_over():
                # checkmate / stalemate
                # 最後に指した側の手番ではない方が負け
                # board.turn は次の手番に進んでいる
                result = "white_win" if board.turn == BLACK else "black_win"
                # 注: 入玉宣言などは上で別処理
                break

            # 千日手判定(やねうら王側でも判定するが念のため)
            try:
                if board.is_repetition():
                    result = "draw"
                    break
            except AttributeError:
                pass
        else:
            # max_ply 到達
            result = "max_ply"

    finally:
        try:
            e_b.quit()
        except Exception:
            pass
        try:
            e_w.quit()
        except Exception:
            pass

    return GameResult(
        game_id=game_id,
        engine_a=eng_black.name,   # 呼び出し元で a/b の対応を取る
        engine_b=eng_white.name,
        a_color="black",
        moves=moves,
        result=result,
        plies=len(moves),
        duration_sec=time.monotonic() - t0,
        sfen=board.sfen(),
    )


# ============== 並列実行 / 集計 ==============


def _run_one(args) -> dict:
    """ProcessPoolExecutor 用のスタブ。trick: dataclass は pickle 可能。"""
    (game_id, eng_a_dict, eng_b_dict, swap, byoyomi_ms, max_ply) = args
    eng_a = EngineDef(**eng_a_dict)
    eng_b = EngineDef(**eng_b_dict)
    if swap:
        eng_black, eng_white = eng_b, eng_a
        a_color = "white"
    else:
        eng_black, eng_white = eng_a, eng_b
        a_color = "black"

    g = play_one_game(game_id, eng_black, eng_white, byoyomi_ms, max_ply=max_ply)

    # a/b 観点に正規化
    raw = g.result  # "black_win" / "white_win" / "draw" / "illegal_*" / "timeout_*" / "max_ply"
    norm = _normalize_result(raw, a_color)
    out = asdict(g)
    out["a_color"] = a_color
    out["result"] = norm
    out["engine_a"] = eng_a.name
    out["engine_b"] = eng_b.name
    return out


def _normalize_result(raw: str, a_color: str) -> str:
    if raw == "draw" or raw == "max_ply":
        return raw  # max_ply は draw 扱いではなく区別して残す
    if raw.endswith("_win"):
        side = raw.split("_")[0]  # black/white
        return "a_win" if side == a_color else "b_win"
    if raw.startswith("illegal_"):
        side = raw.split("_")[1]
        return "illegal_a" if side == a_color else "illegal_b"
    if raw.startswith("timeout_"):
        side = raw.split("_")[1]
        return "timeout_a" if side == a_color else "timeout_b"
    return raw


def _aggregate(results: list[dict]) -> dict:
    wins_a = sum(1 for r in results if r["result"] == "a_win")
    wins_b = sum(1 for r in results if r["result"] == "b_win")
    draws = sum(1 for r in results if r["result"] in ("draw", "max_ply"))
    illegal_or_timeout = sum(
        1 for r in results
        if r["result"].startswith("illegal_") or r["result"].startswith("timeout_")
    )
    stats = MatchStats(
        games=len(results),
        wins_a=wins_a,
        losses_a=wins_b,
        draws=draws,
        illegal_or_timeout=illegal_or_timeout,
    )
    return {
        "games": stats.games,
        "wins_a": stats.wins_a,
        "wins_b": stats.losses_a,
        "draws": stats.draws,
        "illegal_or_timeout": stats.illegal_or_timeout,
        "win_rate_a": stats.win_rate_a,
        "ci95": stats.ci95,
        "elo_diff": stats.elo_diff,
        "elo_ci95": stats.elo_ci95,
        "is_significant": stats.is_significant,
    }


# ============== メイン ==============


def main() -> int:
    ap = argparse.ArgumentParser(description="USIエンジン同士の自己対戦")
    ap.add_argument("--config", required=True, help="対戦シナリオ YAML")
    ap.add_argument("--resume", action="store_true", help="既存出力ディレクトリの続きから(未実装、TODO)")
    args = ap.parse_args()

    config_path = Path(args.config).resolve()
    cfg = load_config(config_path)
    name = cfg["name"]
    games = int(cfg["games"])
    parallel = int(cfg.get("parallel", 1))
    swap_colors = bool(cfg.get("swap_colors", True))
    seed = int(cfg.get("seed", 0))
    byoyomi_ms = int(cfg.get("time_control", {}).get("byoyomi_ms", 1000))

    eng_a = _engine_def_from_dict(cfg["engines"]["a"], config_path)
    eng_b = _engine_def_from_dict(cfg["engines"]["b"], config_path)

    output_root = resolve_path(config_path, cfg["output_dir"])
    assert output_root is not None
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = output_root / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)

    # 設定をコピー保存
    shutil.copy(config_path, out_dir / "config.yaml")

    print(f"[{name}] {games}局, 並列={parallel}, byoyomi={byoyomi_ms}ms, swap_colors={swap_colors}")
    print(f"  a={eng_a.name} ({eng_a.binary})")
    print(f"  b={eng_b.name} ({eng_b.binary})")
    print(f"  out={out_dir}")

    rng = random.Random(seed)
    # 各局の swap フラグを決定
    swaps = [(rng.random() < 0.5) if not swap_colors else (i % 2 == 1) for i in range(games)]

    work_args = [
        (i, asdict(eng_a), asdict(eng_b), swaps[i], byoyomi_ms, 320)
        for i in range(games)
    ]

    results: list[dict] = []
    games_path = out_dir / "games.jsonl"

    with games_path.open("w", encoding="utf-8") as fout:
        if parallel <= 1:
            for wa in work_args:
                r = _run_one(wa)
                results.append(r)
                fout.write(json.dumps(r, ensure_ascii=False) + "\n")
                fout.flush()
                _print_progress(len(results), games, results)
        else:
            with ProcessPoolExecutor(max_workers=parallel, mp_context=mp.get_context("spawn")) as ex:
                futs = {ex.submit(_run_one, wa): wa[0] for wa in work_args}
                for fut in as_completed(futs):
                    r = fut.result()
                    results.append(r)
                    fout.write(json.dumps(r, ensure_ascii=False) + "\n")
                    fout.flush()
                    _print_progress(len(results), games, results)

    summary = _aggregate(results)
    summary["name"] = name
    summary["engine_a"] = eng_a.name
    summary["engine_b"] = eng_b.name
    summary["timestamp"] = timestamp
    with (out_dir / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print()
    print(format_summary(name, MatchStats(
        games=summary["games"],
        wins_a=summary["wins_a"],
        losses_a=summary["wins_b"],
        draws=summary["draws"],
        illegal_or_timeout=summary["illegal_or_timeout"],
    )))
    return 0


def _print_progress(done: int, total: int, results: list[dict]) -> None:
    a = sum(1 for r in results if r["result"] == "a_win")
    b = sum(1 for r in results if r["result"] == "b_win")
    d = sum(1 for r in results if r["result"] in ("draw", "max_ply"))
    print(f"\r[{done}/{total}] a={a} b={b} draws={d}", end="", flush=True)


if __name__ == "__main__":
    sys.exit(main())
