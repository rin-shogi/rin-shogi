"""floodgate_client.py のローカル乾燥テスト用 モック CSA サーバ。

shogi-server / floodgate のプロトコルの最小サブセットを実装し、
固定スクリプトで 1 局を進めて終局までクライアントを誘導する。

スクリプト動作:
    1. LOGIN <user> <pw> を受領 → "LOGIN:<user> OK"
    2. BEGIN Game_Summary 〜 END Game_Summary を送信(クライアントが先手 +)
    3. AGREE <game_id> を受領 → "START:<game_id>"
    4. 対局ループ:
       - クライアントの指し手を受信(echo の代わりに、合法ならそのまま受け入れる)
       - サーバ側で固定の応手を送信(後手の手を1〜2手指す)
       - 数手後 #WIN(クライアント勝ち)+ #END_GAME を送信して終了

このモックサーバは別スレッドで動かし、port を返す。クライアント側のテスト
コードは `floodgate_client.run_session(...)` を直接呼ぶことで end-to-end
動作を確認する。
"""
from __future__ import annotations

import socket
import threading
from typing import Optional


# 後手側の固定応手スクリプト(クライアントが指してきた手数 -> 後手の応手 CSA body)
DEFAULT_OPPONENT_MOVES = [
    "-3334FU",  # 手数1(後手1手目)
    "-8384FU",  # 手数2
    "-2233KA",  # 手数3
]


class MockCsaServer:
    """1 接続 1 対局で終わる最小モックサーバ。"""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 0,  # 0 で自動割当
        username: str = "Rin-suisho5-v1",
        password: str = "test-pw",
        opponent_name: str = "MockOpp",
        game_id: str = "wdoor+test+Rin-suisho5-v1+MockOpp+TESTGAME",
        opponent_moves: Optional[list[str]] = None,
        end_marker: str = "#WIN",
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.opponent_name = opponent_name
        self.game_id = game_id
        self.opponent_moves = list(opponent_moves or DEFAULT_OPPONENT_MOVES)
        self.end_marker = end_marker

        self._listener: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self.error: Optional[Exception] = None
        self.client_lines_received: list[str] = []

    def start(self) -> int:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((self.host, self.port))
        s.listen(1)
        self.port = s.getsockname()[1]
        self._listener = s
        self._thread = threading.Thread(target=self._serve_one, daemon=True)
        self._thread.start()
        return self.port

    def stop(self, join_timeout_s: float = 3.0) -> None:
        if self._listener is not None:
            try:
                self._listener.close()
            except Exception:
                pass
            self._listener = None
        if self._thread is not None:
            self._thread.join(timeout=join_timeout_s)

    def _send(self, sock: socket.socket, lines: list[str]) -> None:
        payload = "\n".join(lines).encode("utf-8") + b"\n"
        sock.sendall(payload)

    def _recv_line(self, sock: socket.socket, buf: bytearray, timeout_s: float = 30.0) -> str:
        sock.settimeout(timeout_s)
        while b"\n" not in buf:
            chunk = sock.recv(4096)
            if not chunk:
                raise ConnectionError("client closed connection")
            buf.extend(chunk)
        nl = buf.index(b"\n")
        line = bytes(buf[:nl]).decode("utf-8", errors="replace").rstrip("\r")
        del buf[: nl + 1]
        self.client_lines_received.append(line)
        return line

    def _game_summary_lines(self) -> list[str]:
        return [
            "BEGIN Game_Summary",
            "Protocol_Version:1.2",
            "Format:Shogi 1.0",
            "Declaration:Jishogi 1.1",
            f"Game_ID:{self.game_id}",
            f"Name+:{self.username}",
            f"Name-:{self.opponent_name}",
            "Your_Turn:+",
            "To_Move:+",
            "BEGIN Time",
            "Time_Unit:1sec",
            "Total_Time:60",
            "Byoyomi:5",
            "Least_Time_Per_Move:0",
            "Increment:0",
            "END Time",
            "BEGIN Position",
            "P1-KY-KE-GI-KI-OU-KI-GI-KE-KY",
            "P2 * -HI *  *  *  *  * -KA *",
            "P3-FU-FU-FU-FU-FU-FU-FU-FU-FU",
            "P4 *  *  *  *  *  *  *  *  *",
            "P5 *  *  *  *  *  *  *  *  *",
            "P6 *  *  *  *  *  *  *  *  *",
            "P7+FU+FU+FU+FU+FU+FU+FU+FU+FU",
            "P8 * +KA *  *  *  *  * +HI *",
            "P9+KY+KE+GI+KI+OU+KI+GI+KE+KY",
            "+",
            "END Position",
            "END Game_Summary",
        ]

    def _serve_one(self) -> None:
        listener = self._listener
        assert listener is not None
        try:
            conn, _addr = listener.accept()
        except OSError:
            return
        buf = bytearray()
        try:
            # 1. LOGIN
            line = self._recv_line(conn, buf)
            expected = f"LOGIN {self.username} {self.password}"
            if line != expected:
                self.error = AssertionError(f"unexpected LOGIN: {line!r}")
                return
            self._send(conn, [f"LOGIN:{self.username} OK"])

            # 2. Game_Summary
            self._send(conn, self._game_summary_lines())

            # 3. AGREE
            line = self._recv_line(conn, buf)
            if not line.startswith(f"AGREE {self.game_id}"):
                self.error = AssertionError(f"unexpected AGREE: {line!r}")
                return
            self._send(conn, [f"START:{self.game_id}"])

            # 4. 対局ループ
            opp_idx = 0
            while True:
                # クライアントの手を受信(echo は不要、ここで直接消費する)
                client_move = self._recv_line(conn, buf, timeout_s=120.0)
                # echo を返す(実サーバ floodgate の動作に合わせる)
                # 時間サフィックスはクライアントが付けてきたものをそのまま返す
                self._send(conn, [client_move])

                # %TORYO / %KACHI ならそこで終局
                if client_move.split(",", 1)[0].startswith("%"):
                    if client_move.startswith("%TORYO"):
                        self._send(conn, ["#LOSE", "#END_GAME"])
                    else:
                        self._send(conn, [self.end_marker, "#END_GAME"])
                    return

                # 後手の応手を送る
                if opp_idx < len(self.opponent_moves):
                    opp_move = self.opponent_moves[opp_idx]
                    opp_idx += 1
                    self._send(conn, [f"{opp_move},T1"])
                else:
                    # スクリプトを使い切ったら勝ち判定で終了
                    self._send(conn, [self.end_marker, "#END_GAME"])
                    return
        except Exception as e:
            self.error = e
        finally:
            try:
                conn.close()
            except Exception:
                pass
