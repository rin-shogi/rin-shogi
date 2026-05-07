"""floodgate アーカイブ棋譜の取得スクリプト(plan E5)。

floodgate(東京大学 shogi-server)のアーカイブから CSA 棋譜を取得して
data/floodgate/ 配下に保存する。

公式アーカイブ場所:
    http://wdoor.c.u-tokyo.ac.jp/shogi/x/  (ディレクトリ構造はサーバ側で変わるので確認すること)

使い方:
    python scripts/floodgate_pgn.py --year 2025 --output ../data/floodgate/2025
    python scripts/floodgate_pgn.py --rating-min 3000 --output ../data/floodgate/strong

実装段階:
    - v0(本ファイル): URL 構造とフィルタの設計のみ。実ダウンロードは TODO
    - v1: アーカイブの zip / tar.bz2 を取得・展開
    - v2: rating によるフィルタリング(棋譜ヘッダから取得)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


DEFAULT_BASE_URL = "http://wdoor.c.u-tokyo.ac.jp/shogi/x/"


def main() -> int:
    ap = argparse.ArgumentParser(description="floodgate アーカイブ取得")
    ap.add_argument("--year", type=int, help="対象年(例: 2025)")
    ap.add_argument("--rating-min", type=int, default=None, help="最低レート(両対局者)")
    ap.add_argument("--output", required=True)
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL)
    args = ap.parse_args()

    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    print(f"[floodgate_pgn] base_url={args.base_url}")
    print(f"  year={args.year}, rating_min={args.rating_min}")
    print(f"  output={out}")
    print("")
    print("v0 骨組み: 実ダウンロード未実装。")
    print("実装 TODO:")
    print(f"  1. {args.base_url} のディレクトリ構造を確認(年・月・週単位の zip / tar.bz2 等)")
    print("  2. requests でダウンロード、md5/sha256 検証(可能なら)")
    print("  3. 展開 → 各 .csa を rating でフィルタ → output 配下に保存")
    print("  4. メタ情報を output/manifest.jsonl に記録(取得日・レート・対局結果 等)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
