"""USIエンジンのプロセス制御ラッパー。

USI プロトコルは行ベースのテキスト通信:
  → engine: usi
  ← engine: id name ...
  ← engine: option name ...
  ← engine: usiok
  → engine: setoption name X value Y
  → engine: isready
  ← engine: readyok
  → engine: usinewgame
  → engine: position startpos moves 7g7f 8c8d
  → engine: go byoyomi 1000
  ← engine: info ...
  ← engine: bestmove 2g2f
  → engine: quit

本クラスは thin な subprocess ラッパーで、コマンド送受信と特定行の待機をサポートする。
"""
from __future__ import annotations

import subprocess
import threading
import time
from collections import deque
from pathlib import Path


class UsiEngine:
    def __init__(
        self,
        binary: str | Path,
        cwd: str | Path | None = None,
        startup_timeout: float = 30.0,
    ) -> None:
        self.binary = str(binary)
        self.cwd = str(cwd) if cwd else None
        self._proc: subprocess.Popen | None = None
        self._reader_thread: threading.Thread | None = None
        self._lines: deque[str] = deque()
        self._lock = threading.Lock()
        self._stopped = False
        self.startup_timeout = startup_timeout

    # --- ライフサイクル ---

    def start(self) -> None:
        self._proc = subprocess.Popen(
            [self.binary],
            cwd=self.cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader_thread.start()

    def quit(self, kill_timeout: float = 5.0) -> None:
        if self._proc is None:
            return
        try:
            self.send("quit")
        except Exception:
            pass
        try:
            self._proc.wait(timeout=kill_timeout)
        except subprocess.TimeoutExpired:
            self._proc.kill()
        self._stopped = True

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.quit()

    # --- 入出力 ---

    def send(self, line: str) -> None:
        if self._proc is None or self._proc.stdin is None:
            raise RuntimeError("engine not started")
        self._proc.stdin.write(line + "\n")
        self._proc.stdin.flush()

    def _reader_loop(self) -> None:
        assert self._proc is not None
        assert self._proc.stdout is not None
        for raw in self._proc.stdout:
            line = raw.rstrip("\r\n")
            with self._lock:
                self._lines.append(line)

    def _pop_line(self) -> str | None:
        with self._lock:
            if self._lines:
                return self._lines.popleft()
        return None

    def wait_for(self, prefix: str, timeout: float = 10.0) -> str:
        """先頭が prefix と一致する行を timeout 秒以内に拾う。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = self._pop_line()
            if line is None:
                time.sleep(0.005)
                continue
            if line.startswith(prefix):
                return line
            # それ以外の行は捨てる(必要なら呼び出し側で別バッファに溜める拡張を)
        raise TimeoutError(f"USI: '{prefix}' を {timeout}s 以内に受信できませんでした")

    def drain(self) -> list[str]:
        out = []
        while True:
            line = self._pop_line()
            if line is None:
                return out
            out.append(line)

    # --- USI 高レベル ---

    def usi_handshake(self) -> None:
        self.send("usi")
        self.wait_for("usiok", timeout=self.startup_timeout)

    def setoption(self, name: str, value) -> None:
        self.send(f"setoption name {name} value {value}")

    def setoptions(self, options: dict | None) -> None:
        if not options:
            return
        for k, v in options.items():
            self.setoption(k, v)

    def isready(self, timeout: float = 60.0) -> None:
        self.send("isready")
        self.wait_for("readyok", timeout=timeout)

    def usinewgame(self) -> None:
        self.send("usinewgame")

    def position(self, startpos: str = "startpos", moves: list[str] | None = None) -> None:
        cmd = f"position {startpos}"
        if moves:
            cmd += " moves " + " ".join(moves)
        self.send(cmd)

    def go_and_get_bestmove(self, go_args: str, timeout: float = 60.0) -> tuple[str, str | None]:
        """`go ...` を投げ bestmove 行を待つ。戻り値は (bestmove, ponder_or_None)。

        bestmove の値は USI 文字列(例: "7g7f", "resign", "win")。
        """
        self.send(f"go {go_args}")
        line = self.wait_for("bestmove", timeout=timeout)
        # 形式: "bestmove <move> [ponder <move>]"
        toks = line.split()
        if len(toks) < 2:
            raise ValueError(f"unexpected bestmove line: {line}")
        bestmove = toks[1]
        ponder = None
        if len(toks) >= 4 and toks[2] == "ponder":
            ponder = toks[3]
        return bestmove, ponder

    def stop(self) -> None:
        self.send("stop")
