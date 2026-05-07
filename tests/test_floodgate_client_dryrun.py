"""floodgate_client.py の end-to-end 乾燥テスト(モック CSA サーバ + Fake USI Engine)。

実 floodgate には接続せず、ローカル mock サーバ + UsiEngine モックで
1 局のフローを完走させ、棋譜・ログが正しく書かれることを検証する。

実行(リポジトリ root から):
    python tests/test_floodgate_client_dryrun.py
"""
from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from tests.mock_csa_server import MockCsaServer  # noqa: E402

import floodgate_client  # noqa: E402


class FakeUsiEngine:
    """UsiEngine API 互換のテスト用ダミー。subprocess を作らない。"""

    def __init__(self, moves: list[str]) -> None:
        self._moves = list(moves)
        self._idx = 0
        self.last_position: str = ""
        self.handshake_done = False
        self.ready_done = False

    # --- ライフサイクル ---
    def start(self) -> None:
        pass

    def quit(self, kill_timeout: float = 5.0) -> None:
        pass

    def usi_handshake(self) -> None:
        self.handshake_done = True

    def setoption(self, name, value) -> None:
        pass

    def setoptions(self, options) -> None:
        pass

    def isready(self, timeout: float = 60.0) -> None:
        self.ready_done = True

    def usinewgame(self) -> None:
        pass

    def position(self, startpos="startpos", moves=None) -> None:
        self.last_position = (startpos, list(moves or []))

    def go_and_get_bestmove(self, go_args, timeout=60.0):
        if self._idx < len(self._moves):
            bm = self._moves[self._idx]
            self._idx += 1
        else:
            bm = "resign"
        return bm, None

    def stop(self) -> None:
        pass


def run_test() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        kifu_dir = td_path / "kifu"
        log_dir = td_path / "results" / "floodgate" / "Rin-suisho5-v1"
        kifu_dir.mkdir(parents=True)
        log_dir.mkdir(parents=True)

        # config を tmp に書き、相対パスで kifu/log を tmp 内に向ける
        # config_path は tmp 配下、相対パス基準も tmp になる
        config_path = td_path / "floodgate_v1.yaml"
        # 適当な絶対パスは付けず、tmp 配下のサブディレクトリ参照で書く
        config_path.write_text(
            """name: Rin-suisho5-v1
mode: floodgate
server:
  host: 127.0.0.1
  port: 0  # 後でテスト側で書き換え
account:
  username: Rin-suisho5-v1
  password: $env:FLOODGATE_PASSWORD
engine:
  binary: dummy-not-used
  options:
    Threads: 1
log_dir: ./results/floodgate/Rin-suisho5-v1
kifu_dir: ./kifu
auto_reconnect: false
max_games_per_session: 1
log_level: INFO
""",
            encoding="utf-8",
        )

        # モックサーバ起動
        password = "mock-password-XYZ"
        server = MockCsaServer(
            username="Rin-suisho5-v1",
            password=password,
            opponent_moves=["-3334FU", "-8384FU", "-2233KA"],
            end_marker="#WIN",
        )
        port = server.start()

        # config を port で書き換え
        cfg_text = config_path.read_text(encoding="utf-8")
        cfg_text = cfg_text.replace("port: 0", f"port: {port}")
        config_path.write_text(cfg_text, encoding="utf-8")

        # 環境変数注入(mock サーバが期待するパスワード)
        os.environ["FLOODGATE_PASSWORD"] = password

        # _start_engine を Fake に差し替え
        # クライアントは先手 +、6 手しかないと仮定して 4 手 + その後 resign で終局
        fake_moves = ["7g7f", "2g2f", "2f2e", "8h2b+"]
        floodgate_client._start_engine = lambda cfg, cp: FakeUsiEngine(fake_moves)

        # config を読み込んで run_session 実行
        from utils.config import load_config

        cfg = load_config(config_path)
        try:
            n = floodgate_client.run_session(cfg, config_path)
        finally:
            server.stop()

        if server.error is not None:
            raise RuntimeError(f"mock server error: {server.error}")

        assert n == 1, f"完了対局数 != 1: {n}"
        print(f"  ok ran 1 game (returned {n})")

        # 棋譜が書き出されているか
        kifu_files = list((td_path / "kifu").rglob("*.csa"))
        assert len(kifu_files) == 1, f"kifu file 数: {kifu_files}"
        kifu = kifu_files[0]
        body = kifu.read_text(encoding="utf-8")
        # ヘッダが含まれている
        assert "BEGIN Game_Summary" in body
        assert "Name+:Rin-suisho5-v1" in body
        # クライアントの 1 手目の echo が含まれている(7776FU)
        assert "+7776FU" in body, body
        # 終局マーカーが含まれている(#CHUDAN は終局直後の RST タイミングで発生しうる)
        assert any(m in body for m in ("#WIN", "#LOSE", "#DRAW", "#CHUDAN")), body
        # パスワードが含まれていない
        assert password not in body, "棋譜にパスワードが漏洩!"
        print(f"  ok kifu written: {kifu.name} ({len(body)} bytes)")

        # log.jsonl に 1 行
        log_jsonl = td_path / "results" / "floodgate" / "Rin-suisho5-v1" / "log.jsonl"
        assert log_jsonl.exists(), "log.jsonl が存在しない"
        lines = log_jsonl.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1, f"log.jsonl 行数: {len(lines)}"
        rec = json.loads(lines[0])
        assert rec["game_id"] == server.game_id
        assert rec["my_color"] == "+"
        assert rec["opponent"] == "MockOpp"
        assert rec["moves"] >= 1
        # パスワード漏洩チェック
        assert password not in lines[0], "log.jsonl にパスワードが漏洩!"
        print(f"  ok log.jsonl appended: {rec['result_marker']} (moves={rec['moves']})")

        # クライアントが期待した順に LOGIN / AGREE / 指し手を送ったか
        sent = server.client_lines_received
        assert sent[0] == f"LOGIN Rin-suisho5-v1 {password}"
        assert any(line.startswith("AGREE ") for line in sent)
        assert any(line.startswith("+7776FU") for line in sent), sent
        print(f"  ok server received expected commands ({len(sent)} lines)")


def main() -> int:
    print("test_floodgate_client_dryrun.py")
    run_test()
    print("ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
