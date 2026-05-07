"""csa.py の単体テスト(pytest 不要、socket.socketpair でモック)。

実行:
    python scripts/utils/test_csa.py
"""
from __future__ import annotations

import socket
import sys
import threading
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent))

from utils.csa import (  # noqa: E402
    CsaClient,
    CsaMoveEvent,
    CsaProtocolError,
    EndGame,
    GameSummary,
    mask_password,
)


def _make_paired_client(username: str = "Rin-test", password: str = "secret123") -> tuple[CsaClient, socket.socket]:
    """paired socket でつないだ CsaClient と、対向(サーバ役)socket を返す。

    本物の `connect()` は呼ばず、socketpair の片方を _sock に直接埋め込む。
    """
    s1, s2 = socket.socketpair()
    client = CsaClient(host="dummy", port=0, username=username, password=password)
    client._sock = s1
    s1.settimeout(5.0)
    return client, s2


def _send_lines(server_sock: socket.socket, lines: list[str]) -> None:
    payload = "\n".join(lines).encode("utf-8") + b"\n"
    server_sock.sendall(payload)


def _recv_all_until_close(server_sock: socket.socket, max_bytes: int = 65536) -> bytes:
    """対向 socket が閉じられるまで読む。テスト末尾の検証用。"""
    server_sock.settimeout(2.0)
    buf = b""
    try:
        while len(buf) < max_bytes:
            chunk = server_sock.recv(4096)
            if not chunk:
                break
            buf += chunk
    except socket.timeout:
        pass
    return buf


def test_mask_password():
    assert mask_password("LOGIN Rin-test secret123", "secret123") == "LOGIN Rin-test ********"
    assert mask_password("hello", "secret123") == "hello"
    assert mask_password("hello", None) == "hello"
    assert mask_password("hello", "") == "hello"
    print("  ok mask_password")


def test_send_recv_roundtrip():
    client, server = _make_paired_client()
    try:
        client.send_line("HELLO")
        # サーバ側は HELLO\n を受け取る
        data = b""
        server.settimeout(2.0)
        while not data.endswith(b"\n"):
            data += server.recv(4096)
        assert data == b"HELLO\n", f"send_line: {data!r}"

        _send_lines(server, ["WORLD"])
        line = client.recv_line(timeout_s=2.0)
        assert line == "WORLD", f"recv_line: {line!r}"
    finally:
        client.close()
        server.close()
    print("  ok send/recv round trip")


def test_login_ok():
    client, server = _make_paired_client(username="Rin-suisho5-v1", password="pw123")

    def server_role():
        # サーバはまず LOGIN を待ち、OK を返す
        buf = b""
        server.settimeout(2.0)
        while not buf.endswith(b"\n"):
            buf += server.recv(4096)
        assert buf == b"LOGIN Rin-suisho5-v1 pw123\n", f"got {buf!r}"
        _send_lines(server, ["LOGIN:Rin-suisho5-v1 OK"])

    t = threading.Thread(target=server_role, daemon=True)
    t.start()
    client.login(login_timeout_s=5.0)
    t.join(timeout=3.0)
    client.close()
    server.close()
    print("  ok login OK")


def test_login_rejected():
    client, server = _make_paired_client(username="Rin-suisho5-v1", password="wrong")

    def server_role():
        server.settimeout(2.0)
        buf = b""
        while not buf.endswith(b"\n"):
            buf += server.recv(4096)
        _send_lines(server, ["LOGIN:incorrect"])

    t = threading.Thread(target=server_role, daemon=True)
    t.start()
    try:
        client.login(login_timeout_s=5.0)
    except CsaProtocolError as e:
        assert "incorrect" in str(e), str(e)
    else:
        raise AssertionError("login should have raised CsaProtocolError")
    t.join(timeout=3.0)
    client.close()
    server.close()
    print("  ok login rejected")


def test_recv_game_summary():
    client, server = _make_paired_client()

    summary_lines = [
        "BEGIN Game_Summary",
        "Protocol_Version:1.2",
        "Format:Shogi 1.0",
        "Declaration:Jishogi 1.1",
        "Game_ID:wdoor+floodgate-300-10F+Rin-suisho5-v1+OPP+20260507193000",
        "Name+:Rin-suisho5-v1",
        "Name-:OPP",
        "Your_Turn:+",
        "To_Move:+",
        "BEGIN Time",
        "Time_Unit:1sec",
        "Total_Time:300",
        "Byoyomi:10",
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

    def server_role():
        _send_lines(server, summary_lines)

    t = threading.Thread(target=server_role, daemon=True)
    t.start()
    summary = client.recv_game_summary(wait_timeout_s=5.0)
    t.join(timeout=2.0)

    assert isinstance(summary, GameSummary)
    assert summary.game_id == "wdoor+floodgate-300-10F+Rin-suisho5-v1+OPP+20260507193000"
    assert summary.your_turn == "+"
    assert summary.to_move == "+"
    assert summary.name_black == "Rin-suisho5-v1"
    assert summary.name_white == "OPP"
    assert summary.total_time_s == 300
    assert summary.byoyomi_s == 10
    assert summary.increment_s == 0
    assert summary.time_unit == "1sec"
    assert len(summary.position_lines) == 10  # P1-P9 + 手番行
    assert summary.position_lines[-1] == "+"
    assert summary.raw_lines[0] == "BEGIN Game_Summary"
    assert summary.raw_lines[-1] == "END Game_Summary"

    client.close()
    server.close()
    print("  ok recv_game_summary")


def test_agree_and_start():
    client, server = _make_paired_client()

    def server_role():
        server.settimeout(2.0)
        buf = b""
        while not buf.endswith(b"\n"):
            buf += server.recv(4096)
        assert buf.startswith(b"AGREE "), buf
        _send_lines(server, ["START:wdoor+floodgate-300-10F+Rin+OPP+20260507"])

    t = threading.Thread(target=server_role, daemon=True)
    t.start()
    client.agree("wdoor+floodgate-300-10F+Rin+OPP+20260507")
    t.join(timeout=2.0)
    client.close()
    server.close()
    print("  ok agree -> START")


def test_recv_event_move():
    client, server = _make_paired_client()
    _send_lines(server, ["+7776FU,T5"])
    ev = client.recv_event()
    assert isinstance(ev, CsaMoveEvent)
    assert ev.raw == "+7776FU,T5"
    assert ev.body == "+7776FU"
    assert ev.sign == "+"
    assert ev.time_used_s == 5
    client.close()
    server.close()
    print("  ok recv_event(move)")


def test_recv_event_endgame():
    client, server = _make_paired_client()
    # 終局通知 + #END_GAME で区切る(本実装は #END_GAME を境にループ break)
    _send_lines(
        server,
        [
            "#WIN",
            "#END_GAME",
        ],
    )
    ev = client.recv_event()
    assert isinstance(ev, EndGame), type(ev)
    assert ev.marker == "#WIN"
    assert "#END_GAME" in ev.trailing_lines
    client.close()
    server.close()
    print("  ok recv_event(end game)")


def test_send_move_with_and_without_time():
    client, server = _make_paired_client()
    client.send_move("+7776FU", time_used_s=3)
    client.send_move("%TORYO")
    server.settimeout(2.0)
    buf = b""
    while buf.count(b"\n") < 2:
        buf += server.recv(4096)
    lines = buf.decode().splitlines()
    assert lines[0] == "+7776FU,T3", lines
    assert lines[1] == "%TORYO", lines
    client.close()
    server.close()
    print("  ok send_move (with/without time)")


def main() -> int:
    print("test_csa.py")
    test_mask_password()
    test_send_recv_roundtrip()
    test_login_ok()
    test_login_rejected()
    test_recv_game_summary()
    test_agree_and_start()
    test_recv_event_move()
    test_recv_event_endgame()
    test_send_move_with_and_without_time()
    print("ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
