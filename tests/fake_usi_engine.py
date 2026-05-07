"""フェイク USI エンジン(テスト用、subprocess として呼ばれる)。

最小限の USI プロトコルを話すだけのスクリプト。実エンジンの代わりに
floodgate_client.py の subprocess として起動して、対局フローを検証する。

固定応答:
    - usi → "id name FakeUSI" + "id author test" + "usiok"
    - setoption / usinewgame / position → 何もせず黙殺
    - isready → "readyok"
    - go ... → 環境変数 FAKE_USI_MOVES (カンマ区切り) で指定した順に bestmove を返す
                指定が尽きたら "bestmove resign"
    - quit → 終了

stdout バッファリング対策で flush を毎回行う。
"""
from __future__ import annotations

import os
import sys


def main() -> int:
    moves = [m.strip() for m in os.environ.get("FAKE_USI_MOVES", "7g7f").split(",") if m.strip()]
    move_idx = 0

    while True:
        line = sys.stdin.readline()
        if not line:
            return 0
        line = line.rstrip("\r\n")
        if line == "usi":
            print("id name FakeUSI")
            print("id author test")
            print("usiok")
            sys.stdout.flush()
        elif line.startswith("setoption"):
            pass
        elif line == "isready":
            print("readyok")
            sys.stdout.flush()
        elif line == "usinewgame":
            pass
        elif line.startswith("position"):
            pass
        elif line.startswith("go"):
            if move_idx < len(moves):
                bm = moves[move_idx]
                move_idx += 1
            else:
                bm = "resign"
            print(f"bestmove {bm}")
            sys.stdout.flush()
        elif line == "stop":
            pass
        elif line == "quit":
            return 0
        else:
            # 未知コマンドは無視
            pass


if __name__ == "__main__":
    sys.exit(main())
