"""floodgate_client.py の時間制ロジック(純関数)単体テスト。

実行:
    python scripts/utils/test_time_control.py

カバー範囲:
    time_control_from_summary: Game_Summary 値の None / 0 / 正常値の解釈
    build_go_args:             USI go コマンド文字列とタイムアウト計算

特に重要なケース:
    - floodgate-300-10F (5分 + 10秒フィッシャー): byoyomi=0, inc=10
      → byoyomi を送らず binc/winc のみを送る
    - floodgate-900-0 (15分切れ負け): byoyomi=0, inc=0
      → "byoyomi 0" を送る
    - 1分+10秒秒読み: byoyomi=10, inc=0
      → byoyomi を送る、binc/winc は送らない
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent))

from floodgate_client import build_go_args, time_control_from_summary  # noqa: E402


def test_summary_floodgate_300_10F():
    """floodgate-300-10F: Total=300, Byoyomi=0, Increment=10."""
    t, b, i = time_control_from_summary(300, 0, 10)
    assert (t, b, i) == (300_000, 0, 10_000), (t, b, i)
    print("  ok summary: floodgate-300-10F (Total=300, Byo=0, Inc=10)")


def test_summary_byoyomi_only():
    """秒読み制: Total=900, Byoyomi=10, Increment=0."""
    t, b, i = time_control_from_summary(900, 10, 0)
    assert (t, b, i) == (900_000, 10_000, 0), (t, b, i)
    print("  ok summary: byoyomi-only (Total=900, Byo=10, Inc=0)")


def test_summary_sudden_death():
    """切れ負け: Total=900, Byoyomi=0, Increment=0."""
    t, b, i = time_control_from_summary(900, 0, 0)
    assert (t, b, i) == (900_000, 0, 0), (t, b, i)
    print("  ok summary: sudden death (Total=900, Byo=0, Inc=0)")


def test_summary_none_uses_defaults():
    """サーバが値を提供しなかった場合は妥当なデフォルト(300/10/0)。"""
    t, b, i = time_control_from_summary(None, None, None)
    assert (t, b, i) == (300_000, 10_000, 0), (t, b, i)
    # 一部だけ None
    t, b, i = time_control_from_summary(60, None, None)
    assert (t, b, i) == (60_000, 10_000, 0), (t, b, i)
    print("  ok summary: None -> defaults (300/10/0)")


def test_summary_zero_is_respected_not_falsy():
    """0 は明示値なので尊重する(`or` で None 同等にしないこと)。

    これが本問題の根本原因: 旧コードは `byoyomi_s or 10` で 0 を 10 にしていた。
    floodgate-300-10F では Byoyomi=0 が正しい(フィッシャー制)ため、
    0 を 10 に書き換えると engine が時間配分を誤算して投了する事故が起きた。
    """
    t, b, i = time_control_from_summary(0, 0, 0)
    assert (t, b, i) == (0, 0, 0), (t, b, i)
    print("  ok summary: 0 is respected, not coerced to default")


def test_go_args_fischer_no_byoyomi():
    """フィッシャー(inc>0)時: byoyomi は送らず binc/winc を送る。"""
    args, worst = build_go_args(
        btime_ms=300_000, wtime_ms=300_000, byoyomi_ms=0, increment_ms=10_000
    )
    assert args == "btime 300000 wtime 300000 binc 10000 winc 10000", args
    assert "byoyomi" not in args, args
    assert worst == 300_000 + 10_000, worst
    print("  ok go_args: fischer (no byoyomi field)")


def test_go_args_byoyomi_no_inc():
    """秒読み制(inc=0)時: byoyomi を送る、binc/winc は送らない。"""
    args, worst = build_go_args(
        btime_ms=900_000, wtime_ms=900_000, byoyomi_ms=10_000, increment_ms=0
    )
    assert args == "btime 900000 wtime 900000 byoyomi 10000", args
    assert "binc" not in args, args
    assert "winc" not in args, args
    assert worst == 10_000, worst
    print("  ok go_args: byoyomi-only (no binc/winc field)")


def test_go_args_sudden_death_uses_byoyomi_zero():
    """切れ負け(byoyomi=0, inc=0): `byoyomi 0` を送る、worst は btime。"""
    args, worst = build_go_args(
        btime_ms=900_000, wtime_ms=900_000, byoyomi_ms=0, increment_ms=0
    )
    assert args == "btime 900000 wtime 900000 byoyomi 0", args
    assert worst == 900_000, worst
    print("  ok go_args: sudden death (byoyomi 0)")


def test_go_args_does_not_emit_both_byoyomi_and_inc():
    """USI 仕様で undefined な「byoyomi と binc/winc を両方指定」を避ける。

    これも本問題の根本原因の片方: 旧コードは byoyomi を必ず付けた上で
    inc>0 の時に追加で binc/winc も付けていた。
    YaneuraOu が時間配分を誤って投了に至った。
    """
    for byoyomi_ms in (0, 10_000, 60_000):
        for inc_ms in (0, 5_000, 10_000):
            args, _ = build_go_args(300_000, 300_000, byoyomi_ms, inc_ms)
            has_byoyomi = "byoyomi" in args
            has_inc = "binc" in args or "winc" in args
            assert not (has_byoyomi and has_inc), (
                f"byoyomi と binc/winc を同時指定: byoyomi_ms={byoyomi_ms} "
                f"inc_ms={inc_ms} args={args!r}"
            )
    print("  ok go_args: never emits byoyomi + binc/winc together")


def test_go_args_btime_decreases_worst_in_fischer():
    """フィッシャー時、btime が減ると worst_think_ms も減る(消化済みは思考できない)。"""
    _, worst_initial = build_go_args(300_000, 300_000, 0, 10_000)
    _, worst_after_5moves = build_go_args(150_000, 300_000, 0, 10_000)
    assert worst_initial > worst_after_5moves, (worst_initial, worst_after_5moves)
    assert worst_after_5moves == 150_000 + 10_000, worst_after_5moves
    print("  ok go_args: fischer worst tracks current btime")


def main() -> int:
    print("test_time_control.py")
    test_summary_floodgate_300_10F()
    test_summary_byoyomi_only()
    test_summary_sudden_death()
    test_summary_none_uses_defaults()
    test_summary_zero_is_respected_not_falsy()
    test_go_args_fischer_no_byoyomi()
    test_go_args_byoyomi_no_inc()
    test_go_args_sudden_death_uses_byoyomi_zero()
    test_go_args_does_not_emit_both_byoyomi_and_inc()
    test_go_args_btime_decreases_worst_in_fischer()
    print("ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
