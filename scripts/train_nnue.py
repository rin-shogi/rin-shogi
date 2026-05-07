"""NNUE 学習ラッパー(plan D3)。

やねうら王の `learn` USIコマンドを起動し、教師局面から評価関数を学習する。

使い方:
    python scripts/train_nnue.py --config configs/train/train_v0.1.yaml
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


def _build_learn_cmd(args: dict) -> str:
    parts = ["learn"]
    for k, v in args.items():
        if v is None:
            continue
        if isinstance(v, bool):
            v = str(v).lower()
        parts.append(f"{k} {v}")
    return " ".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser(description="やねうら王 learn ラッパー")
    ap.add_argument("--config", required=True)
    ap.add_argument(
        "--end-marker",
        default="learn finished",
        help="完了とみなす出力行のプレフィクス(やねうら王のバージョンにより 'finished_save' 等)",
    )
    ap.add_argument("--max-runtime-sec", type=float, default=None)
    a = ap.parse_args()

    config_path = Path(a.config).resolve()
    cfg = load_config(config_path)

    binary = resolve_path(config_path, cfg["engine_binary"])
    seed_eval = resolve_path(config_path, cfg.get("seed_eval_dir"))
    options = dict(cfg.get("options") or {})
    if seed_eval:
        # 出発点モデルを EvalDir として読み込ませる
        options.setdefault("EvalDir", str(seed_eval))

    learn_args = dict(cfg["learn"])
    targetdir = resolve_path(config_path, learn_args.get("targetdir"))
    if targetdir:
        learn_args["targetdir"] = str(targetdir)
    output_dir = resolve_path(config_path, learn_args.get("output_dir"))
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        # やねうら王 learn は output dir を直接指定するオプションがないバージョンもある
        # その場合は実行後に手動コピー / EvalSaveDir を別途設定
        learn_args["evalsavedir"] = str(output_dir)
        learn_args.pop("output_dir", None)

    val = resolve_path(config_path, learn_args.get("validation_set_file_name"))
    if val:
        learn_args["validation_set_file_name"] = str(val)

    print(f"[train_nnue] name={cfg['name']}")
    print(f"  engine:    {binary}")
    print(f"  seed_eval: {seed_eval}")
    print(f"  targetdir: {targetdir}")
    print(f"  output_dir:{output_dir}")
    cmd = _build_learn_cmd(learn_args)
    print(f"  USI cmd:   {cmd}")

    cwd = binary.parent
    t0 = time.monotonic()
    with UsiEngine(binary, cwd=cwd) as e:
        e.usi_handshake()
        e.setoptions(options)
        e.isready(timeout=300.0)
        e.send(cmd)

        while True:
            if a.max_runtime_sec is not None and (time.monotonic() - t0) > a.max_runtime_sec:
                print("\n[train_nnue] タイムアウト")
                break
            lines = e.drain()
            for line in lines:
                print(line)
                if line.startswith(a.end_marker):
                    print("[train_nnue] 完了マーカー検出")
                    return 0
            time.sleep(1.0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
