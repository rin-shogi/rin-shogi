"""探索パラメータ自動チューニング(plan F3)— 骨組み。

SPSA(Simultaneous Perturbation Stochastic Approximation)風のアルゴリズムで
やねうら王の `setoption` で渡せるパラメータを最適化する。

実装段階:
    - v0(本ファイル): API 設計・骨組みのみ。実評価ループは TODO
    - v1: 各イテレーションで selfplay_match.py 相当の対戦を回し、勝率を勾配近似に使う

参考: SPSA は1イテレーションあたり 2 回の対戦(+δ と −δ の摂動)で
全パラメータの勾配を同時推定する。試行回数は通常 数百〜数千イテレーションが必要。

使い方(将来):
    python scripts/tune_search.py --config configs/tune/spsa_v1.yaml
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from utils.config import load_config  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="探索パラメータ自動チューニング(SPSA)")
    ap.add_argument("--config", required=True)
    args = ap.parse_args()

    cfg = load_config(args.config)
    print("[tune_search] このスクリプトは v0(骨組み)です。")
    print("  対象パラメータ:", list(cfg.get("parameters", {}).keys()))
    print("  予算(イテレーション数):", cfg.get("iterations"))
    print("")
    print("実装 TODO:")
    print("  1. SPSA 摂動 ±δ の評価対戦を selfplay_match.py 経由で回す")
    print("  2. 勝率差から勾配を推定し、パラメータを更新")
    print("  3. 各イテレーションを results/tuning/<run_id>/ に保存")
    print("")
    print("詳細設計は plan の F3 と docs/ITERATION.md を参照。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
