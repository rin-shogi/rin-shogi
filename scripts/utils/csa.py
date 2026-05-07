"""CSA プロトコル(shogi-server / floodgate)TCP クライアント。

floodgate は東京大学が運用する CSA プロトコルベースの将棋エンジン対局サーバ:
    http://wdoor.c.u-tokyo.ac.jp/shogi/floodgate.html

本モジュールは TCP I/O と CSA メッセージのパースに集中する。
USI ↔ CSA 指し手変換は `utils.csa_usi`、対局ループは `floodgate_client.py` 側。

公式仕様(shogi-server):
    http://www.computer-shogi.org/protocol/tcp_ip_server_113.html
    https://github.com/na2hiro/Shogi-server (floodgate で使われている実装)

公開 API:
    CsaClient            — 接続・ログイン・対局・切断のラッパ
    GameSummary          — `BEGIN Game_Summary` 〜 `END Game_Summary` のパース結果
    EndGame              — 終局メッセージ + 後続行
    CsaProtocolError     — プロトコル違反例外
"""
from __future__ import annotations

import logging
import socket
import time
from dataclasses import dataclass, field
from typing import Optional


log = logging.getLogger(__name__)


# 終局メッセージ(指し手スロットに来うる、対局終了を示す行)
END_GAME_MARKERS = {
    "#WIN",
    "#LOSE",
    "#DRAW",
    "#SENNICHITE",
    "#OUTE_SENNICHITE",
    "#JISHOGI",
    "#TIME_UP",
    "#ILLEGAL_MOVE",
    "#ILLEGAL_ACTION",
    "#RESIGN",
    "#KACHI",
    "#TSUMI",
    "#FUZUMI",
    "#MAX_MOVES",
    "#CENSORED",
    "#CHUDAN",
}

# 終局後にサーバから流れてくる追加メッセージのプレフィックス(棋譜に含めるため)
END_GAME_TRAILING_PREFIXES = ("#",)


class CsaProtocolError(Exception):
    """CSA プロトコル違反 / 想定外応答。"""


@dataclass
class GameSummary:
    """`BEGIN Game_Summary` ブロックから抽出した対局メタデータ。

    floodgate のサンプル(Total_Time / Byoyomi / Increment は対局種別による):
        BEGIN Game_Summary
        Protocol_Version:1.2
        Format:Shogi 1.0
        Declaration:Jishogi 1.1
        Game_ID:wdoor+floodgate-300-10F+Rin-suisho5-v1+OPP+20260507193000
        Name+:Rin-suisho5-v1
        Name-:OPP
        Your_Turn:+
        To_Move:+
        BEGIN Time
        Time_Unit:1sec
        Total_Time:300
        Byoyomi:10
        Least_Time_Per_Move:0
        Increment:0
        END Time
        BEGIN Position
        P1-KY-KE-GI-KI-OU-KI-GI-KE-KY
        ...
        +
        END Position
        END Game_Summary
    """

    game_id: str
    your_turn: str  # "+" or "-"
    to_move: str  # "+" or "-"
    name_black: str  # Name+:
    name_white: str  # Name-:
    total_time_s: Optional[int] = None
    byoyomi_s: Optional[int] = None
    increment_s: Optional[int] = None
    least_time_per_move_s: Optional[int] = None
    time_unit: str = "1sec"
    # Position ブロック(CSA 形式生テキスト、棋譜ヘッダにそのまま使う)
    position_lines: list[str] = field(default_factory=list)
    # raw 全行(棋譜ヘッダ復元用)
    raw_lines: list[str] = field(default_factory=list)

    @property
    def my_color(self) -> str:
        return self.your_turn


@dataclass
class CsaMoveEvent:
    """サーバから受信した 1 手(指し手 または特殊コマンド %TORYO/%KACHI 等の echo)。"""

    raw: str  # サーバから受信した行そのまま("+7776FU,T5" 等)
    body: str  # ",T<n>" を剥がした手("+7776FU" / "%TORYO")
    sign: Optional[str]  # "+" or "-"。特殊コマンド(%XXX)では None
    time_used_s: Optional[int]

    @property
    def is_special(self) -> bool:
        return self.body.startswith("%")


@dataclass
class EndGame:
    """対局終了。終局マーカー + 後続行(`#END_GAME` などサーバが流す残り)を保持する。"""

    marker: str  # "#WIN", "#LOSE", ...
    trailing_lines: list[str] = field(default_factory=list)


def mask_password(line: str, password: Optional[str]) -> str:
    """ログ出力用にパスワード部分を伏せる。"""
    if password and password in line:
        return line.replace(password, "*" * 8)
    return line


class CsaClient:
    """floodgate(shogi-server)接続クライアント。

    使い方(対局 1 局):
        with CsaClient(host, port, user, pw) as c:
            c.login()
            summary = c.recv_game_summary()
            c.agree(summary.game_id)
            while True:
                ev = c.recv_event()
                if isinstance(ev, EndGame):
                    break
                # ev は CsaMoveEvent
                ...
                c.send_move("+7776FU", time_used_s=3)

    Note:
        本クラスは "1 セッション = 1 対局完了 + 切断" を前提とした薄いラッパ。
        複数対局の自動継続・再ログインは呼び出し側(floodgate_client.py)が制御する。
    """

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        *,
        connect_timeout_s: float = 30.0,
        recv_timeout_s: float = 60.0,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.connect_timeout_s = connect_timeout_s
        self.recv_timeout_s = recv_timeout_s

        self._sock: Optional[socket.socket] = None
        self._buf: bytes = b""

    # ---- ライフサイクル ----

    def connect(self) -> None:
        sock = socket.create_connection((self.host, self.port), timeout=self.connect_timeout_s)
        sock.settimeout(self.recv_timeout_s)
        self._sock = sock
        self._buf = b""
        log.info("CSA: connected to %s:%d", self.host, self.port)

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
            log.info("CSA: socket closed")

    def __enter__(self) -> "CsaClient":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # ---- 低レベル送受信 ----

    def send_line(self, line: str) -> None:
        """1 行送信(末尾改行は本メソッドで付与)。"""
        if self._sock is None:
            raise CsaProtocolError("socket not connected")
        data = (line + "\n").encode("utf-8")
        log.debug("CSA send: %s", mask_password(line, self.password))
        self._sock.sendall(data)

    def recv_line(self, timeout_s: Optional[float] = None) -> str:
        """1 行受信(改行で区切る)。タイムアウト時は socket.timeout を投げる。"""
        if self._sock is None:
            raise CsaProtocolError("socket not connected")
        if timeout_s is not None:
            self._sock.settimeout(timeout_s)
        try:
            while b"\n" not in self._buf:
                chunk = self._sock.recv(4096)
                if not chunk:
                    raise CsaProtocolError("connection closed by peer")
                self._buf += chunk
            line, _, rest = self._buf.partition(b"\n")
            self._buf = rest
            decoded = line.decode("utf-8", errors="replace").rstrip("\r")
            log.debug("CSA recv: %s", mask_password(decoded, self.password))
            return decoded
        finally:
            if timeout_s is not None:
                self._sock.settimeout(self.recv_timeout_s)

    # ---- ログイン ----

    def login(self, login_timeout_s: float = 30.0) -> None:
        """`LOGIN <user> <password>` を送り、`LOGIN:<user> OK` を待つ。"""
        self.send_line(f"LOGIN {self.username} {self.password}")
        deadline = time.monotonic() + login_timeout_s
        while time.monotonic() < deadline:
            line = self.recv_line(timeout_s=max(1.0, deadline - time.monotonic()))
            if line.startswith(f"LOGIN:{self.username} OK"):
                log.info("CSA: login OK as %s", self.username)
                return
            if line.startswith("LOGIN:incorrect"):
                raise CsaProtocolError("login rejected (incorrect username/password)")
            # その他の出力(挨拶など)は捨てて待つ
        raise CsaProtocolError("login timeout")

    def logout(self) -> None:
        """`LOGOUT` を送る。サーバ応答は待たない(切断前提)。"""
        try:
            self.send_line("LOGOUT")
        except Exception:
            pass

    # ---- Game_Summary 受信 ----

    def recv_game_summary(self, wait_timeout_s: float = 3600.0) -> GameSummary:
        """サーバから `BEGIN Game_Summary` ブロックを受信してパース。

        対局の割り当て待ち時間が長い(ペア成立まで数十分かかることも)ので、
        `wait_timeout_s` はデフォルト 1 時間とした。呼び出し側で短縮可。
        """
        deadline = time.monotonic() + wait_timeout_s
        # BEGIN Game_Summary を待つ
        while True:
            remain = deadline - time.monotonic()
            if remain <= 0:
                raise CsaProtocolError("game summary wait timeout")
            line = self.recv_line(timeout_s=remain)
            if line == "BEGIN Game_Summary":
                break
            # それ以外は捨てる(ハートビートなど想定)

        raw_lines: list[str] = ["BEGIN Game_Summary"]
        in_time = False
        in_position = False
        time_kv: dict[str, str] = {}
        position_lines: list[str] = []
        kv: dict[str, str] = {}

        while True:
            line = self.recv_line()
            raw_lines.append(line)
            if line == "END Game_Summary":
                break
            if line == "BEGIN Time":
                in_time = True
                continue
            if line == "END Time":
                in_time = False
                continue
            if line == "BEGIN Position":
                in_position = True
                continue
            if line == "END Position":
                in_position = False
                continue
            if in_position:
                position_lines.append(line)
                continue
            if ":" in line:
                k, _, v = line.partition(":")
                if in_time:
                    time_kv[k] = v
                else:
                    kv[k] = v

        # 必須フィールドを取り出す
        try:
            game_id = kv["Game_ID"]
            your_turn = kv["Your_Turn"]
            to_move = kv["To_Move"]
            name_black = kv["Name+"]
            name_white = kv["Name-"]
        except KeyError as e:
            raise CsaProtocolError(f"Game_Summary に必須フィールドがありません: {e}")

        def _int_or_none(d: dict[str, str], key: str) -> Optional[int]:
            v = d.get(key)
            if v is None or v == "":
                return None
            try:
                return int(v)
            except ValueError:
                return None

        summary = GameSummary(
            game_id=game_id,
            your_turn=your_turn,
            to_move=to_move,
            name_black=name_black,
            name_white=name_white,
            total_time_s=_int_or_none(time_kv, "Total_Time"),
            byoyomi_s=_int_or_none(time_kv, "Byoyomi"),
            increment_s=_int_or_none(time_kv, "Increment"),
            least_time_per_move_s=_int_or_none(time_kv, "Least_Time_Per_Move"),
            time_unit=time_kv.get("Time_Unit", "1sec"),
            position_lines=position_lines,
            raw_lines=raw_lines,
        )
        log.info(
            "CSA: Game_Summary received id=%s your_turn=%s opponent=%s",
            summary.game_id,
            summary.your_turn,
            summary.name_white if summary.your_turn == "+" else summary.name_black,
        )
        return summary

    def agree(self, game_id: str) -> None:
        """`AGREE <game_id>` を送信。サーバが `START:<game_id>` を返したら対局開始。"""
        self.send_line(f"AGREE {game_id}")
        # START:<game_id> または REJECT:<...> を待つ
        line = self.recv_line(timeout_s=60.0)
        if line.startswith(f"START:{game_id}"):
            log.info("CSA: game START id=%s", game_id)
            return
        if line.startswith(f"REJECT:{game_id}"):
            raise CsaProtocolError(f"game rejected by server: {line}")
        raise CsaProtocolError(f"unexpected response after AGREE: {line!r}")

    def reject(self, game_id: str) -> None:
        """`REJECT <game_id>` を送信して対局を断る。"""
        self.send_line(f"REJECT {game_id}")

    # ---- 指し手スロット ----

    def recv_event(self) -> object:
        """指し手 1 行を受信し、`CsaMoveEvent` または `EndGame` を返す。

        終局時はマーカー受領後、続けて `#END_GAME` 等の追加行が降ってくるので、
        次の指し手スロットが始まるまで(または socket timeout / 切断まで)読み続けて
        `EndGame.trailing_lines` に格納する。
        """
        line = self.recv_line()
        if line in END_GAME_MARKERS:
            end = EndGame(marker=line)
            # 後続行を回収。サーバ側が close するまで or タイムアウトまで。
            # 実用上、終局後は数行で終わるので短いタイムアウトで済む。
            try:
                while True:
                    extra = self.recv_line(timeout_s=5.0)
                    end.trailing_lines.append(extra)
                    # サーバ側で対局リソース解放。次の対局オファーが来る or 切断。
                    # 終局メッセージ後の "#END_GAME" を見たら一旦区切る。
                    if extra == "#END_GAME":
                        break
            except (socket.timeout, CsaProtocolError, OSError):
                # OSError 包含: 終局直後にサーバが close することがあるが、
                # 対局結果はマーカー受領時点で確定しているので無視して return。
                pass
            return end

        # 指し手行 or 特殊コマンド(%TORYO/%KACHI 等の echo)
        body = line
        time_used: Optional[int] = None
        if "," in line:
            head, _, tail = line.partition(",")
            body = head
            if tail.startswith("T"):
                try:
                    time_used = int(tail[1:])
                except ValueError:
                    time_used = None
        if body.startswith("%"):
            return CsaMoveEvent(raw=line, body=body, sign=None, time_used_s=time_used)
        if not body or body[0] not in "+-":
            raise CsaProtocolError(f"unexpected line on move slot: {line!r}")
        return CsaMoveEvent(raw=line, body=body, sign=body[0], time_used_s=time_used)

    def send_move(self, csa_body: str, time_used_s: Optional[int] = None) -> None:
        """色付き CSA 指し手("+7776FU" 等)、または特殊コマンド("%TORYO" 等)を送信。

        `time_used_s` が与えられたら ",T<n>" を末尾に付ける。
        """
        if time_used_s is None:
            self.send_line(csa_body)
        else:
            self.send_line(f"{csa_body},T{int(time_used_s)}")
