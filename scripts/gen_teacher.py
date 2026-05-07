"""教師局面生成ラッパー(plan D1)。

やねうら王の `gensfen` USIコマンドを起動し、教師局面ファイルを出力する。
本ラッパーは USIプロセスを spawn し、設定 (`setoption`) を反映してから `gensfen` を発行、
完了行(`gensfen finished` 等)または `quit` まで stdout を中継する。

使い方:
    python scripts/gen_teacher.py --config configs/train/gensfen_v1.yaml
"""
from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from utils.config import load_config, resolve_path  # noqa: E402
from utils.usi import UsiEngine  # noqa: E402


def _build_gensfen_cmd(args: dict) -> str:
    parts = ["gensfen"]
    for k, v in args.items():
        if v is None:
            continue
        if isinstance(v, bool):
            v = str(v).lower()
        parts.append(f"{k} {v}")
    return " ".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser(description="やねうら王 gensfen ラッパー")
    ap.add_argument("--config", required=True)
    ap.add_argument(
        "--end-marker",
        default="gensfen finished",
        help="完了とみなす出力行のプレフィクス(やねうら王のバージョンで異なる場合あり)",
    )
    ap.add_argument(
        "--max-runtime-sec",
        type=float,
        default=None,
        help="保険のタイムアウト(指定なしなら無制限)",
    )
    a = ap.parse_args()

    config_path = Path(a.config).resolve()
    cfg = load_config(config_path)

    binary = resolve_path(config_path, cfg["engine_binary"])
    eval_dir = resolve_path(config_path, cfg.get("eval_dir"))
    options = dict(cfg.get("options") or {})
    if eval_dir:
        options.setdefault("EvalDir", str(eval_dir))

    gensfen_args = dict(cfg["gensfen"])
    output_path = resolve_path(config_path, gensfen_args.get("output_file_name"))
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        gensfen_args["output_file_name"] = str(output_path)

    print(f"[gen_teacher] name={cfg['name']}")
    print(f"  engine: {binary}")
    print(f"  eval:   {eval_dir}")
    print(f"  output: {output_path}")
    print(f"  loop:   {gensfen_args.get('loop')}")
    print(f"  depth:  {gensfen_args.get('depth')}")

    cmd = _build_gensfen_cmd(gensfen_args)
    print(f"  USI cmd: {cmd}")

    cwd = binary.parent
    t0 = time.monotonic()
    with UsiEngine(binary, cwd=cwd) as e:
        e.usi_handshake()
        e.setoptions(options)
        e.isready(timeout=120.0)
        e.send(cmd)

        # gensfen の進捗行を中継しつつ end_marker を待つ
        while True:
            if a.max_runtime_sec is not None and (time.monotonic() - t0) > a.max_runtime_sec:
                print("\n[gen_teacher] タイムアウト、stop を投げます")
                e.stop()
                break
            lines = e.drain()
            for line in lines:
                print(line)
                if line.startswith(a.end_marker):
                    print("[gen_teacher] 完了マーカー検出")
                    return 0
            time.sleep(0.5)
    return 0


if __name__ == "__main__":
    sys.exit(main())
