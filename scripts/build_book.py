"""定跡 DB 構築スクリプト(plan F2)。

複数ソース(やねうら王 .db / CSA棋譜ディレクトリ / KIF棋譜ディレクトリ)から局面と指し手を集約し、
頻度ベースで採用 → (任意で)評価関数による再評価フィルタを掛けて、やねうら王形式の定跡 .db に出力する。

使い方:
    python scripts/build_book.py --config configs/book/base.yaml

実装段階:
    - v0(本ファイル): CSA棋譜の取り込みと頻度集計、出力フォーマット決め打ち。フィルタは TODO
    - v1: 評価関数フィルタ実装
    - v2: KIF棋譜・統計ベース重み付け

備考: やねうら王の定跡フォーマットは
    sfen <局面sfen> <手番> <手数>
    <move> <ponder> <value> <depth> <count>
    <move> ...
    (空行)
    sfen ...
の形式が主流(バージョンにより微差)。
"""
from __future__ import annotations

import argparse
import collections
import sys
from pathlib import Path

try:
    import cshogi  # noqa: F401
    from cshogi import Board, BLACK, WHITE
    from cshogi import CSA  # CSA 棋譜パーサ
except ImportError:
    print("ERROR: cshogi が必要です。pip install -r requirements.txt", file=sys.stderr)
    raise

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from utils.config import load_config, resolve_path  # noqa: E402


def _iter_csa_files(d: Path):
    yield from sorted(d.rglob("*.csa"))


def _parse_csa_to_book_entries(csa_path: Path, max_ply: int) -> list[tuple[str, str]]:
    """CSA 1ファイルから (sfen_before_move, usi_move) のリストを返す。"""
    out: list[tuple[str, str]] = []
    try:
        parser = CSA.Parser.parse_file(str(csa_path))
        if not parser:
            return out
        # cshogi の CSA.Parser.parse_file はリストを返すバージョンと単体を返すバージョンがある
        records = parser if isinstance(parser, list) else [parser]
    except Exception as ex:
        print(f"  WARN: parse 失敗 {csa_path}: {ex}", file=sys.stderr)
        return out

    for rec in records:
        board = Board()
        moves = rec.moves
        for i, mv in enumerate(moves):
            if i >= max_ply:
                break
            sfen = board.sfen()
            try:
                # cshogi の move は数値、USI 文字列に変換
                from cshogi import move_to_usi
                usi_move = move_to_usi(mv)
            except Exception:
                break
            out.append((sfen, usi_move))
            try:
                board.push(mv)
            except Exception:
                break
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="定跡 DB 構築")
    ap.add_argument("--config", required=True)
    a = ap.parse_args()

    config_path = Path(a.config).resolve()
    cfg = load_config(config_path)

    out_db = resolve_path(config_path, cfg["output_db"])
    assert out_db is not None
    out_db.parent.mkdir(parents=True, exist_ok=True)

    counter: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)

    for src in cfg.get("sources", []):
        stype = src["type"]
        weight = float(src.get("weight", 1.0))
        if stype == "csa_dir":
            d = resolve_path(config_path, src["path"])
            if not d or not d.exists():
                print(f"WARN: {d} が存在しません、スキップ")
                continue
            max_ply = int(src.get("max_ply", 30))
            print(f"[csa_dir] {d} max_ply={max_ply} weight={weight}")
            n = 0
            for csa in _iter_csa_files(d):
                for sfen, usi_move in _parse_csa_to_book_entries(csa, max_ply):
                    counter[sfen][usi_move] += weight
                n += 1
            print(f"  -> {n} files processed")

        elif stype == "yaneuraou_db":
            # TODO: やねうら王 .db テキスト形式の取り込み
            print(f"[yaneuraou_db] TODO: {src['path']} の取り込み未実装")

        elif stype == "kif_dir":
            # TODO: KIF パース
            print(f"[kif_dir] TODO: {src['path']} の取り込み未実装")

        else:
            print(f"WARN: 未対応のソース種別: {stype}")

    filtering = cfg.get("filtering", {}) or {}
    min_count = int(filtering.get("min_count", 1))

    eval_filter = filtering.get("evaluator", {}) or {}
    if eval_filter.get("enable"):
        print("[filter] 評価関数フィルタ: TODO(v1 で実装)")
        # ここでエンジン起動 → 各局面の候補手を評価 → 閾値以下を除外する処理を入れる予定

    # 出力(やねうら王の標準的な定跡フォーマットを最小実装)
    print(f"[output] {out_db}")
    n_pos = 0
    n_move = 0
    with out_db.open("w", encoding="utf-8") as f:
        for sfen, moves in counter.items():
            kept = [(m, c) for m, c in moves.items() if c >= min_count]
            if not kept:
                continue
            # 手番・手数は sfen 文字列の末尾の数値から取る(cshogi の sfen は手数まで含む)
            f.write(f"sfen {sfen}\n")
            for m, c in sorted(kept, key=lambda x: -x[1]):
                # value/depth は未計測なら 0、count は出現回数
                f.write(f"{m} none 0 0 {int(c)}\n")
            f.write("\n")
            n_pos += 1
            n_move += len(kept)

    print(f"[done] positions={n_pos}, moves={n_move}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
