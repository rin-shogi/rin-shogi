"""floodgate(shogi-server)接続クライアント(plan E2)— 骨組み。

CSA プロトコルでサーバに接続し、自エンジン(USIエンジン)を介して対局する。

実装段階:
    - v0(本ファイル): API 設計・骨組みのみ。CSA <-> USI 翻訳と sock 通信は TODO
    - v1: ログイン → 待ち受け → 1局完走 → ログ保存
    - v2: 自動再接続・複数セッション・レーティング監視

参考実装:
    - 公式 shogi-server リポジトリの Ruby クライアント
    - 既存の Python 実装: 例 yaneuraou-floodgate-client (要調査)

使い方(将来):
    $env:FLOODGATE_PASSWORD = "your-password"
    python scripts/floodgate_client.py --config configs/match/floodgate_v1.yaml
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from utils.config import load_config, resolve_path  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="floodgate (shogi-server) クライアント")
    ap.add_argument("--config", required=True)
    args = ap.parse_args()

    config_path = Path(args.config).resolve()
    cfg = load_config(config_path)

    server = cfg.get("server", {})
    account = cfg.get("account", {})
    engine_cfg = cfg.get("engine", {})

    print("[floodgate_client] v0 骨組み")
    print(f"  server: {server.get('host')}:{server.get('port')}")
    print(f"  user:   {account.get('username')}")
    print(f"  engine: {resolve_path(config_path, engine_cfg.get('binary'))}")
    print("")
    print("実装 TODO(優先順):")
    print("  1. socket で host:port に TCP 接続、CSA LOGIN コマンドを発行")
    print("  2. 'LOGIN: ... OK' を確認、待ち受け")
    print("  3. 'BEGIN Game_Summary' を解釈し、自分の手番・持ち時間・初期局面を取得")
    print("  4. USIエンジンを utils/usi.py で起動、`position` / `go byoyomi N` を発行")
    print("  5. bestmove を CSA に翻訳して送信、相手の手を待つ → 局面を更新 → 繰り返し")
    print("  6. 終局信号(#WIN/#LOSE/#DRAW/#CENSORED 等)で 1 局終了、棋譜を保存")
    print("  7. auto_reconnect=true なら再接続ループ")
    print("")
    print("注: CSA <-> USI の指し手翻訳ユーティリティが必要。utils/csa_usi.py を新設する想定。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
