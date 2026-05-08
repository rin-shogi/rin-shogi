"""floodgate(shogi-server)接続クライアント — 本実装。

CSA プロトコルでサーバに接続し、USIエンジン(やねうら王)を介して対局する。

使い方:
    1. リポジトリ root の `.env` に FLOODGATE_PASSWORD を設定
    2. `configs/match/floodgate_v1.yaml` を編集(handle 名・エンジンパス等)
    3. 実行:
       python scripts/floodgate_client.py --config configs/match/floodgate_v1.yaml

機能:
    - .env から FLOODGATE_PASSWORD 等を自動ロード(python-dotenv)
    - USI エンジンを subprocess 起動、対局ごとに usinewgame で初期化
    - CSA プロトコルでログイン → Game_Summary 受領 → AGREE → 対局ループ
    - 対局棋譜を kifu/yyyy/mm/dd/<game_id>.csa に保存
    - 対局結果サマリを <log_dir>/log.jsonl に追記
    - 自動再接続(切断時 30s 待機、連続 5 回失敗で停止)
    - 1 セッション最大対局数 / Ctrl-C グレースフル停止
    - 認証情報の漏洩防止: 棋譜書込前に password が含まれていないことを assert
"""
from __future__ import annotations

import argparse
import json
import logging
import signal
import socket
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import cshogi
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from utils.config import load_config, resolve_path  # noqa: E402
from utils.csa import (  # noqa: E402
    CsaClient,
    CsaProtocolError,
    EndGame,
    GameSummary,
    mask_password,
)
from utils.csa_usi import (  # noqa: E402
    csa_move_to_usi,
    push_csa_move,
    usi_move_to_csa,
)
from utils.usi import UsiEngine  # noqa: E402


log = logging.getLogger("floodgate_client")


# --- 時間制ユーティリティ(ユニットテスト対象、純関数) ---

def time_control_from_summary(
    total_time_s: Optional[int],
    byoyomi_s: Optional[int],
    increment_s: Optional[int],
) -> tuple[int, int, int]:
    """Game_Summary の時間関連フィールドから (total_ms, byoyomi_ms, inc_ms) を返す。

    None は「サーバが値を提供しなかった」とみなして妥当なデフォルトを当てる。
    0 は「明示的に値なし(切れ負け側 / フィッシャー側)」なので 0 のまま尊重する。
    `or` を使って 0 を None 同等にしないことが重要。
    """
    t = (total_time_s if total_time_s is not None else 300) * 1000
    b = (byoyomi_s if byoyomi_s is not None else 10) * 1000
    i = (increment_s if increment_s is not None else 0) * 1000
    return t, b, i


def build_go_args(
    btime_ms: int, wtime_ms: int, byoyomi_ms: int, increment_ms: int
) -> tuple[str, int]:
    """USI go コマンドの引数文字列と、エンジン応答の安全タイムアウト(ms)を返す。

    USI 仕様では byoyomi と binc/winc は択一が原則なので、
    increment > 0 ならフィッシャー、それ以外なら byoyomi を選ぶ。
    切れ負け(byoyomi=0, inc=0)も byoyomi 0 として表現できる。

    Returns:
        (go_args, worst_think_ms)
    """
    if increment_ms > 0:
        go_args = (
            f"btime {btime_ms} wtime {wtime_ms} "
            f"binc {increment_ms} winc {increment_ms}"
        )
        worst = btime_ms + increment_ms
    else:
        go_args = f"btime {btime_ms} wtime {wtime_ms} byoyomi {byoyomi_ms}"
        worst = byoyomi_ms if byoyomi_ms > 0 else btime_ms
    return go_args, worst


# --- グレースフル停止フラグ(Ctrl-C で立てる) ---
_stop_requested = False


def _install_sigint_handler() -> None:
    def handler(signum, frame):
        global _stop_requested
        _stop_requested = True
        log.warning("SIGINT 受信。進行中の対局を完走後に停止します。")

    signal.signal(signal.SIGINT, handler)


@dataclass
class GameResult:
    game_id: str
    opponent: str
    my_color: str  # "+" or "-"
    result_marker: str  # "#WIN", "#LOSE", ...
    moves: int
    duration_s: int
    started_at: str  # ISO8601 UTC
    kifu_path: str


def _kifu_dir_for(base_dir: Path, started_at_dt: datetime) -> Path:
    """`kifu/yyyy/mm/dd/` ディレクトリを返す(なければ作る)。"""
    d = base_dir / f"{started_at_dt:%Y}" / f"{started_at_dt:%m}" / f"{started_at_dt:%d}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe_game_id(game_id: str) -> str:
    """ファイル名に使える形にサニタイズ(+, : 等を _ に)。"""
    safe = "".join(c if c.isalnum() or c in "-._" else "_" for c in game_id)
    return safe or "unknown"


def _write_kifu(kifu_path: Path, raw_lines: list[str], password: Optional[str]) -> None:
    """棋譜を CSA 形式で書き出す。書込前にパスワード漏洩チェック。"""
    body = "\n".join(raw_lines) + "\n"
    if password and password in body:
        raise RuntimeError("棋譜にパスワードが含まれています。書込中止。")
    kifu_path.write_text(body, encoding="utf-8", newline="\n")
    log.info("kifu saved: %s (%d lines)", kifu_path, len(raw_lines))


def _append_log_jsonl(log_path: Path, result: GameResult) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(result.__dict__, ensure_ascii=False) + "\n")


def _start_engine(cfg: dict, config_path: Path) -> UsiEngine:
    engine_cfg = cfg.get("engine", {})
    binary = resolve_path(config_path, engine_cfg.get("binary"))
    cwd = engine_cfg.get("cwd")
    cwd_resolved = resolve_path(config_path, cwd) if cwd else None
    usi = UsiEngine(binary=binary, cwd=cwd_resolved)
    usi.start()
    usi.usi_handshake()
    options = engine_cfg.get("options") or {}
    # EvalDir / BookFile は config からの相対パスを絶対化
    for key in ("EvalDir", "BookFile", "BookDir"):
        if key in options and isinstance(options[key], str):
            options[key] = str(resolve_path(config_path, options[key]))
    usi.setoptions(options)
    usi.isready()
    log.info("USI engine started: %s", binary)
    return usi


def play_one_game(
    usi: UsiEngine,
    csa: CsaClient,
    summary: GameSummary,
    kifu_root: Path,
    log_path: Path,
    *,
    password: Optional[str],
) -> GameResult:
    """1 局完走させる。終局メッセージを受領するまで戻らない。

    floodgate の初期局面は Hirate(平手)前提。Position ブロックを cshogi で
    パースする実装は将来必要なら拡張する。
    """
    started_at_dt = datetime.now(timezone.utc)
    started_at_iso = started_at_dt.isoformat(timespec="seconds")
    started_monotonic = time.monotonic()

    board = cshogi.Board()  # Hirate
    usi.usinewgame()
    usi_moves: list[str] = []

    # 棋譜の生行: Game_Summary をそのまま、その後に START 行
    raw_lines: list[str] = list(summary.raw_lines)
    raw_lines.append(f"START:{summary.game_id}")

    my_color = summary.your_turn
    total_time_ms, byoyomi_ms, increment_ms = time_control_from_summary(
        summary.total_time_s, summary.byoyomi_s, summary.increment_s
    )
    btime_ms = total_time_ms
    wtime_ms = total_time_ms

    log.info(
        "対局開始: %s vs %s (Total=%ds, Byoyomi=%ds, Increment=%ds, my_color=%s)",
        summary.name_black, summary.name_white,
        total_time_ms // 1000, byoyomi_ms // 1000, increment_ms // 1000, my_color,
    )

    opponent = summary.name_white if my_color == "+" else summary.name_black

    result_marker = "#UNKNOWN"

    while True:
        is_my_turn = (
            (my_color == "+" and board.turn == cshogi.BLACK)
            or (my_color == "-" and board.turn == cshogi.WHITE)
        )

        if is_my_turn:
            # 思考と送信
            usi.position("startpos", moves=usi_moves)
            go_args, worst_think_ms = build_go_args(
                btime_ms, wtime_ms, byoyomi_ms, increment_ms
            )
            log.info(
                "go (move=%d, btime=%dms, wtime=%dms, inc=%dms): %s",
                len(usi_moves) + 1, btime_ms, wtime_ms, increment_ms, go_args,
            )
            think_start = time.monotonic()
            # 想定最悪(btime+inc) + ネットワーク遅延 + 60秒の安全マージン
            timeout_s = max(worst_think_ms / 1000, 5.0) + 60.0
            try:
                bestmove, _ = usi.go_and_get_bestmove(go_args, timeout=timeout_s)
            except TimeoutError as e:
                # 1次フォールバック: stop コマンドで bestmove を回収する。
                # ハング ではなく単に思考オーバーランの場合、stop で現時点の
                # 最善手が即返るので投了せずに済む。
                log.warning(
                    "go timeout (%.1fs) — stop コマンド送出して bestmove を回収します",
                    timeout_s,
                )
                try:
                    usi.stop()
                    line = usi.wait_for("bestmove", timeout=10.0)
                    toks = line.split()
                    bestmove = toks[1] if len(toks) >= 2 else "resign"
                    log.info("stop で bestmove 回収成功: %s", bestmove)
                except Exception as e2:
                    log.error(
                        "stop 後も bestmove 未返却。投了に切り替え: %s", e2
                    )
                    csa.send_move(
                        "%TORYO",
                        time_used_s=int(time.monotonic() - think_start),
                    )
                    ev = csa.recv_event()
                    if isinstance(ev, EndGame):
                        result_marker = ev.marker
                        raw_lines.append(ev.marker)
                        raw_lines.extend(ev.trailing_lines)
                    break
            except Exception as e:
                log.error("USI go error (非タイムアウト): %s — 投了", e)
                csa.send_move(
                    "%TORYO", time_used_s=int(time.monotonic() - think_start)
                )
                ev = csa.recv_event()
                if isinstance(ev, EndGame):
                    result_marker = ev.marker
                    raw_lines.append(ev.marker)
                    raw_lines.extend(ev.trailing_lines)
                break

            elapsed_s = max(0, int(time.monotonic() - think_start))

            if bestmove == "resign":
                csa.send_move("%TORYO", time_used_s=elapsed_s)
            elif bestmove == "win":
                csa.send_move("%KACHI", time_used_s=elapsed_s)
            else:
                try:
                    csa_body = usi_move_to_csa(bestmove, board)
                except ValueError as e:
                    log.error("USI->CSA 変換失敗 (bestmove=%r sfen=%s): %s",
                              bestmove, board.sfen(), e)
                    csa.send_move("%TORYO", time_used_s=elapsed_s)
                    bestmove = None
                else:
                    csa.send_move(csa_body, time_used_s=elapsed_s)

            # 自分の手の echo を待つ。サーバが echo してから終局通知する場合と
            # echo せずに即終局通知する場合の両方に対応(下の recv_event で分岐)。

        # サーバからの次の出力を受信(自分の手の echo / 相手の手 / 終局)
        try:
            ev = csa.recv_event()
        except (socket.timeout, CsaProtocolError, OSError) as e:
            # OSError 包含: ConnectionResetError / ConnectionAbortedError 等。
            # サーバが終局直後に即 close した場合に発生しうる(対局結果は確定済み)。
            log.warning("recv_event interrupted: %s", e)
            result_marker = "#CHUDAN"
            raw_lines.append(result_marker)
            break

        if isinstance(ev, EndGame):
            result_marker = ev.marker
            raw_lines.append(ev.marker)
            raw_lines.extend(ev.trailing_lines)
            break

        # CsaMoveEvent
        raw_lines.append(ev.raw)

        if ev.is_special:
            # %TORYO / %KACHI 等の echo。次に終局メッセージが来る想定。
            continue

        # 通常の指し手 echo / 相手の手
        try:
            usi_str = csa_move_to_usi(ev.body, board)
            push_csa_move(board, ev.body)
        except ValueError as e:
            log.error("CSA->USI 変換失敗 (csa=%r sfen=%s): %s",
                      ev.body, board.sfen(), e)
            # 反則レベルの不整合。投了して切る。
            csa.send_move("%TORYO")
            result_marker = "#ABORT"
            break

        usi_moves.append(usi_str)

        # 残り時間更新(その手を指した側の時間を消費)
        if ev.time_used_s is not None:
            used_ms = ev.time_used_s * 1000
            # 直前の手を指したのは、push 後の現在手番の「逆」
            mover_was_black = board.turn == cshogi.WHITE
            if mover_was_black:
                btime_ms = max(0, btime_ms - used_ms + increment_ms)
            else:
                wtime_ms = max(0, wtime_ms - used_ms + increment_ms)

    duration_s = int(time.monotonic() - started_monotonic)

    # 棋譜ファイルパス
    kifu_dir = _kifu_dir_for(kifu_root, started_at_dt)
    kifu_path = kifu_dir / f"{_safe_game_id(summary.game_id)}.csa"
    try:
        _write_kifu(kifu_path, raw_lines, password)
    except RuntimeError as e:
        log.error("棋譜書込失敗: %s", e)

    result = GameResult(
        game_id=summary.game_id,
        opponent=opponent,
        my_color=my_color,
        result_marker=result_marker,
        moves=len(usi_moves),
        duration_s=duration_s,
        started_at=started_at_iso,
        kifu_path=str(kifu_path),
    )
    _append_log_jsonl(log_path, result)
    log.info(
        "game finished: %s %s vs %s (moves=%d, %ds)",
        result_marker,
        summary.name_black if my_color == "+" else summary.name_white,
        opponent,
        result.moves,
        result.duration_s,
    )
    return result


def run_session(cfg: dict, config_path: Path) -> int:
    """1 プロセス分のセッションを走らせる(自動再接続つき)。

    Returns: 完了対局数
    """
    server = cfg.get("server", {})
    account = cfg.get("account", {})
    host = server.get("host", "wdoor.c.u-tokyo.ac.jp")
    port = int(server.get("port", 4081))
    username = account.get("username")
    if not username:
        raise RuntimeError("account.username が未設定です")

    # floodgate CSA モードのパスワード組み立て:
    #   game_type + trip が両方あればそれを優先(`<game_type>,<trip>`)、
    #   なければ後方互換のため password を使う(任意の文字列、マッチメイキング非対応)
    game_type = account.get("game_type")
    trip = account.get("trip")
    if game_type and trip:
        password = f"{game_type},{trip}"
        log.info("floodgate game_type=%s でマッチメイキングに参加します", game_type)
    elif "password" in account and account["password"]:
        password = account["password"]
        log.warning(
            "account.password を直接使用(game_type+trip 未設定のため "
            "floodgate のマッチメイキングキューに入らない可能性あり)"
        )
    else:
        raise RuntimeError(
            "account.game_type + account.trip(推奨)または account.password が必要です"
        )

    log_dir = resolve_path(config_path, cfg.get("log_dir", "../results/floodgate"))
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_jsonl = log_dir / "log.jsonl"

    kifu_root = resolve_path(config_path, cfg.get("kifu_dir", "../kifu"))
    kifu_root = Path(kifu_root)
    kifu_root.mkdir(parents=True, exist_ok=True)

    auto_reconnect = bool(cfg.get("auto_reconnect", True))
    max_games = cfg.get("max_games_per_session")
    max_games = None if max_games in (None, "null", 0) else int(max_games)
    reconnect_wait_s = float(cfg.get("reconnect_wait_sec", 30))
    max_failures = int(cfg.get("max_consecutive_failures", 5))

    games_completed = 0
    consecutive_failures = 0

    while True:
        if _stop_requested:
            log.info("停止要求あり。セッション終了。")
            break
        if max_games is not None and games_completed >= max_games:
            log.info("max_games_per_session=%d 到達。終了。", max_games)
            break

        usi: Optional[UsiEngine] = None
        try:
            usi = _start_engine(cfg, config_path)
            with CsaClient(host, port, username, password) as csa:
                csa.login()
                while True:
                    if _stop_requested:
                        break
                    if max_games is not None and games_completed >= max_games:
                        break
                    log.info("対局割り当て待ち...(games_completed=%d)", games_completed)
                    summary = csa.recv_game_summary()
                    csa.agree(summary.game_id)
                    play_one_game(
                        usi, csa, summary, kifu_root, log_jsonl, password=password
                    )
                    games_completed += 1
                    consecutive_failures = 0
                # graceful logout
                csa.logout()
            return games_completed
        except (CsaProtocolError, socket.error, OSError) as e:
            # 直前に対局を完走している場合、これは「対局後にサーバが close した」
            # 想定通りの挙動なので warning ではなく info 扱い・短い再接続インターバル。
            graceful_after_game = (
                games_completed > 0 and consecutive_failures == 0
            )
            consecutive_failures += 1
            if graceful_after_game:
                wait_s = float(cfg.get("post_game_wait_sec", 3))
                log.info(
                    "対局後にサーバが切断(正常)。%d 秒後に再接続して次の対局を待ちます。",
                    int(wait_s),
                )
            else:
                wait_s = reconnect_wait_s
                log.warning(
                    "セッション失敗 [%d/%d]: %s",
                    consecutive_failures,
                    max_failures,
                    mask_password(str(e), password),
                )
            if not auto_reconnect:
                raise
            if consecutive_failures >= max_failures:
                log.error("連続失敗が上限 %d に到達。停止。", max_failures)
                raise
            if not graceful_after_game:
                log.info("%d 秒後に再接続します。", int(wait_s))
            time.sleep(wait_s)
        finally:
            if usi is not None:
                try:
                    usi.quit()
                except Exception:
                    pass

    return games_completed


def setup_logging(cfg: dict) -> None:
    level_name = (cfg.get("log_level") or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="floodgate (shogi-server) クライアント")
    ap.add_argument("--config", required=True, help="YAML 設定ファイルへのパス")
    ap.add_argument("--env", default=None, help=".env のパス(既定: リポジトリ root の .env)")
    ap.add_argument(
        "--username",
        default=None,
        help="config の account.username を上書き(対話起動用)",
    )
    ap.add_argument(
        "--game-type",
        default=None,
        help="config の account.game_type を上書き",
    )
    args = ap.parse_args()

    # .env ロード(明示パス or デフォルト探索)。既存環境変数は上書きしない
    # (bat 等が環境変数を先に set している場合はそちらを尊重)。
    if args.env:
        load_dotenv(args.env)
    else:
        # スクリプトの2つ上(scripts/.. = リポジトリ root)を見る
        repo_root = SCRIPT_DIR.parent
        env_path = repo_root / ".env"
        if env_path.exists():
            load_dotenv(env_path)
        else:
            load_dotenv()  # cwd フォールバック

    config_path = Path(args.config).resolve()
    cfg = load_config(config_path)

    # CLI 引数で account.username / account.game_type を上書き
    if args.username:
        cfg.setdefault("account", {})["username"] = args.username
    if args.game_type:
        cfg.setdefault("account", {})["game_type"] = args.game_type

    setup_logging(cfg)

    _install_sigint_handler()

    log.info("floodgate_client start (config=%s)", config_path)
    try:
        n = run_session(cfg, config_path)
        log.info("セッション完了: %d 局", n)
        return 0
    except Exception as e:
        log.exception("致命的エラー: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
