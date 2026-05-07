"""csa_usi.py の単体テスト(pytest 不要、`__main__` で assert ベース)。

実行:
    python scripts/utils/test_csa_usi.py
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent))  # scripts/ を import パスに

import cshogi  # noqa: E402

from utils.csa_usi import (  # noqa: E402
    csa_move_to_usi,
    parse_csa_move_line,
    push_csa_move,
    push_usi_move,
    usi_move_to_csa,
)


def test_parse_csa_move_line():
    """CSA 1 行のパース。色記号・時間サフィックス・特殊コマンドの分解。"""
    cases = [
        # (input, expected body, sign, time_s, special)
        ("+7776FU", "+7776FU", "+", None, None),
        ("-3334FU,T5", "-3334FU", "-", 5, None),
        ("+0055FU,T0", "+0055FU", "+", 0, None),
        ("%TORYO", "%TORYO", None, None, "%TORYO"),
        ("%KACHI,T3", "%KACHI", None, 3, "%KACHI"),
        ("  +2222UM,T120  ", "+2222UM", "+", 120, None),
    ]
    for line, body, sign, time_s, special in cases:
        got = parse_csa_move_line(line)
        assert got.body == body, f"{line!r}: body {got.body!r} != {body!r}"
        assert got.sign == sign, f"{line!r}: sign {got.sign!r} != {sign!r}"
        assert got.time_s == time_s, f"{line!r}: time_s {got.time_s!r} != {time_s!r}"
        assert got.special == special, f"{line!r}: special {got.special!r} != {special!r}"
        assert got.is_special == (special is not None)
    print(f"  ok parse_csa_move_line ({len(cases)} cases)")


def test_basic_round_trip():
    """初期局面からの代表手を CSA -> USI -> CSA で round-trip する。"""
    cases = [
        # (CSA with sign, expected USI, expected CSA back)
        ("+7776FU", "7g7f", "+7776FU"),  # 先手 ▲7六歩
        ("+2726FU", "2g2f", "+2726FU"),  # 先手 ▲2六歩
        ("+5756FU", "5g5f", "+5756FU"),  # 先手 ▲5六歩
        ("+8822UM", "8h2b+", "+8822UM"),  # 先手 ▲2二角成
        ("+7968GI", "7i6h", "+7968GI"),  # 先手 ▲6八銀
    ]
    for csa, expected_usi, expected_csa in cases:
        b = cshogi.Board()
        if csa == "+8822UM":
            # 角成は他の手を進めてからにする
            for setup in ["+7776FU", "-3334FU"]:
                push_csa_move(b, setup)
        usi = csa_move_to_usi(csa, b)
        assert usi == expected_usi, f"{csa}: usi {usi!r} != {expected_usi!r}"
        # Board は変えずに USI->CSA round trip
        b2 = b.copy()
        csa_back = usi_move_to_csa(usi, b2)
        assert csa_back == expected_csa, f"{csa}: round trip {csa_back!r} != {expected_csa!r}"
    print(f"  ok basic round trip ({len(cases)} cases)")


def test_drop_round_trip():
    """駒打ちの round-trip。先手・後手の両方をテスト。"""
    # 玉だけの局面 + 先手が歩を持っている
    b_black = cshogi.Board("4k4/9/9/9/9/9/9/9/4K4 b P 1")
    csa = "+0055FU"
    usi = csa_move_to_usi(csa, b_black)
    assert usi == "P*5e", f"先手歩打ち USI: {usi!r}"
    csa_back = usi_move_to_csa(usi, b_black)
    assert csa_back == csa, f"先手歩打ち round trip: {csa_back!r}"

    # 後手が歩を持っている
    b_white = cshogi.Board("4k4/9/9/9/9/9/9/9/4K4 w p 1")
    csa = "-0055FU"
    usi = csa_move_to_usi(csa, b_white)
    assert usi == "P*5e", f"後手歩打ち USI: {usi!r}"
    csa_back = usi_move_to_csa(usi, b_white)
    assert csa_back == csa, f"後手歩打ち round trip: {csa_back!r}"
    print("  ok drop round trip (sente / gote)")


def test_promotion_round_trip():
    """成りの round-trip。CSA は成った後の駒種、USI は + サフィックスで表現。"""
    # 飛車成りができる局面: 5七に飛車のみ、5二まで間に駒なし、玉は遠ざける
    b = cshogi.Board("9/9/9/9/9/9/4R4/9/k7K b - 1")
    csa = "+5752RY"  # 飛車を5七から5二に成り
    usi = csa_move_to_usi(csa, b)
    assert usi == "5g5b+", f"成りの USI: {usi!r}"
    csa_back = usi_move_to_csa(usi, b)
    assert csa_back == csa, f"成りの round trip: {csa_back!r}"
    print("  ok promotion round trip")


def test_special_commands():
    """特殊コマンドの USI <-> CSA 変換。Board は不要(変換テーブル)。"""
    b = cshogi.Board()
    # USI -> CSA
    assert usi_move_to_csa("resign", b) == "%TORYO"
    assert usi_move_to_csa("win", b) == "%KACHI"
    # CSA -> USI
    assert csa_move_to_usi("%TORYO", b) == "resign"
    assert csa_move_to_usi("%KACHI", b) == "win"
    print("  ok special commands (resign / win)")


def test_color_assignment():
    """色記号の付与は board.turn から決まる。先手番 -> "+", 後手番 -> "-"."""
    b = cshogi.Board()
    assert b.turn == cshogi.BLACK
    csa = usi_move_to_csa("7g7f", b)
    assert csa.startswith("+"), csa
    push_usi_move(b, "7g7f")
    assert b.turn == cshogi.WHITE
    csa2 = usi_move_to_csa("3c3d", b)
    assert csa2.startswith("-"), csa2
    print("  ok color assignment from board.turn")


def test_push_helpers():
    """push_csa_move / push_usi_move が局面を正しく進めること。"""
    b1 = cshogi.Board()
    push_csa_move(b1, "+7776FU")
    push_usi_move(b1, "3c3d")
    sfen1 = b1.sfen()

    b2 = cshogi.Board()
    push_usi_move(b2, "7g7f")
    push_csa_move(b2, "-3334FU")
    sfen2 = b2.sfen()

    assert sfen1 == sfen2, f"push helpers の挙動不一致: {sfen1!r} vs {sfen2!r}"
    print("  ok push helpers consistency")


def test_invalid_input_raises():
    """不正入力で ValueError が出ること。"""
    b = cshogi.Board()
    # 色記号なし
    try:
        csa_move_to_usi("7776FU", b)
    except ValueError:
        pass
    else:
        raise AssertionError("色記号なし CSA で ValueError が出ないといけない")
    # 不正な USI(初期局面で 9九が空ではないので無理)
    try:
        usi_move_to_csa("9i9a", b)
    except ValueError:
        pass
    else:
        raise AssertionError("不正な USI で ValueError が出ないといけない")
    print("  ok invalid input raises")


def main() -> int:
    print("test_csa_usi.py")
    test_parse_csa_move_line()
    test_basic_round_trip()
    test_drop_round_trip()
    test_promotion_round_trip()
    test_special_commands()
    test_color_assignment()
    test_push_helpers()
    test_invalid_input_raises()
    print("ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
