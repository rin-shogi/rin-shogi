"""CSA <-> USI 指し手変換ユーティリティ。

floodgate(CSA プロトコル)とやねうら王(USI)の橋渡しに使う。
内部の指し手表現・合法性チェックは cshogi に委譲し、本モジュールは
floodgate 流の文字列(色付き・時間サフィックス・特殊コマンド)と
USI 文字列との相互変換のみを担う。

CSA 指し手フォーマット(本モジュールが扱う形):
    "<sign><from><to><piece>[,T<sec>]"
    例: "+7776FU"      = 先手 7七から7六へ歩
        "-3334FU,T5"   = 後手 3三から3四へ歩、消費5秒
        "+0055FU"      = 先手 5五に歩を打つ(from が 00)
        "+2233UM"      = 先手 2二から3三へ角成(駒種は成った後の駒)

特殊 CSA コマンド(指し手スロットに来うるもの):
    "%TORYO"     = 投了                              ↔ USI "resign"
    "%KACHI"     = 入玉宣言勝ち(27点法)             ↔ USI "win"
    "%CHUDAN"    = 中断(本ブリッジでは送らない)
    "%TIME_UP"   = 時間切れ(本ブリッジでは送らない)
    "%ILLEGAL_MOVE" = 反則(本ブリッジでは送らない)

cshogi の `Board.move_from_csa` / `cshogi.move_to_csa` は色記号(+/-)を
含まない CSA 形式("7776FU")を扱うため、本モジュールで色記号と時間
サフィックスの剥がし/付与を行う。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import cshogi


# ---- 特殊コマンドの相互変換テーブル ----
USI_TO_CSA_SPECIAL = {
    "resign": "%TORYO",
    "win": "%KACHI",
}
CSA_TO_USI_SPECIAL = {v: k for k, v in USI_TO_CSA_SPECIAL.items()}


@dataclass
class CsaMoveLine:
    """floodgate サーバから受信した 1 手分の行を分解した結果。

    raw 文字列の例: "+7776FU,T5"

    Attributes:
        body:    色記号と駒種までを含む CSA 移動文字列(例: "+7776FU")。
                 cshogi に渡すときはさらに sign を剥がして使う。
        sign:    "+" または "-"(先手/後手)
        time_s:  消費秒数(",T<n>" 由来。無ければ None)
        special: 特殊コマンドの場合の値("%TORYO" など)。指し手なら None。
    """

    body: str
    sign: Optional[str]
    time_s: Optional[int]
    special: Optional[str]

    @property
    def is_special(self) -> bool:
        return self.special is not None


def parse_csa_move_line(line: str) -> CsaMoveLine:
    """floodgate からの 1 行を `CsaMoveLine` に分解する。

    入力例:
        "+7776FU,T5"      -> body="+7776FU", sign="+", time_s=5,  special=None
        "-3334FU"         -> body="-3334FU", sign="-", time_s=None, special=None
        "%TORYO"          -> body="%TORYO",  sign=None, time_s=None, special="%TORYO"
        "%TORYO,T0"       -> body="%TORYO",  sign=None, time_s=0,    special="%TORYO"
    """
    s = line.strip()
    time_s: Optional[int] = None
    if "," in s:
        head, _, tail = s.partition(",")
        if tail.startswith("T"):
            try:
                time_s = int(tail[1:])
            except ValueError:
                time_s = None
        s = head
    if s.startswith("%"):
        return CsaMoveLine(body=s, sign=None, time_s=time_s, special=s)
    if not s or s[0] not in "+-":
        raise ValueError(f"CSA 指し手行に色記号がありません: {line!r}")
    return CsaMoveLine(body=s, sign=s[0], time_s=time_s, special=None)


def csa_move_to_usi(csa_body: str, board: cshogi.Board) -> str:
    """色付き CSA 指し手("+7776FU" 等)を USI 文字列("7g7f")に変換する。

    特殊コマンド("%TORYO" 等)は USI 側の対応文字列("resign" 等)を返す。
    cshogi が解釈できない場合は ValueError。
    """
    if csa_body in CSA_TO_USI_SPECIAL:
        return CSA_TO_USI_SPECIAL[csa_body]
    if not csa_body or csa_body[0] not in "+-":
        raise ValueError(f"色記号 +/- が必要: {csa_body!r}")
    cshogi_form = csa_body[1:]  # cshogi は色記号なし
    move_int = board.move_from_csa(cshogi_form)
    if move_int == 0:
        raise ValueError(f"cshogi が指し手として解釈できません: {csa_body!r} (sfen={board.sfen()})")
    usi = cshogi.move_to_usi(move_int)
    if usi is None:
        raise ValueError(f"cshogi.move_to_usi が None を返しました: {csa_body!r}")
    return usi


def usi_move_to_csa(usi: str, board: cshogi.Board) -> str:
    """USI 文字列("7g7f" / "P*5e" / "2b3a+" / "resign" / "win")を
    色付き CSA 指し手("+7776FU" 等)に変換する。

    色記号は board.turn から自動付与する(BLACK="+", WHITE="-")。
    """
    if usi in USI_TO_CSA_SPECIAL:
        return USI_TO_CSA_SPECIAL[usi]
    move_int = board.move_from_usi(usi)
    if move_int == 0:
        raise ValueError(f"cshogi が指し手として解釈できません: {usi!r} (sfen={board.sfen()})")
    csa_body = cshogi.move_to_csa(move_int)
    if csa_body is None:
        raise ValueError(f"cshogi.move_to_csa が None を返しました: {usi!r}")
    sign = "+" if board.turn == cshogi.BLACK else "-"
    return sign + csa_body


def push_csa_move(board: cshogi.Board, csa_body: str) -> None:
    """色付き CSA 指し手で局面を進める。"""
    if not csa_body or csa_body[0] not in "+-":
        raise ValueError(f"色記号 +/- が必要: {csa_body!r}")
    move_int = board.move_from_csa(csa_body[1:])
    if move_int == 0:
        raise ValueError(f"不正な指し手: {csa_body!r}")
    board.push(move_int)


def push_usi_move(board: cshogi.Board, usi: str) -> None:
    """USI 指し手で局面を進める。"""
    move_int = board.move_from_usi(usi)
    if move_int == 0:
        raise ValueError(f"不正な指し手: {usi!r}")
    board.push(move_int)
