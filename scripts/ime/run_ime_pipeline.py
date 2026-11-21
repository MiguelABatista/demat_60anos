"""Executa o processo isolado de concluintes do IME (download -> parse -> lista OBM-U no IME).

Uso:
    .venv/bin/python scripts/ime/run_ime_pipeline.py              # usa HTMLs em cache
    .venv/bin/python scripts/ime/run_ime_pipeline.py --download   # baixa HTMLs faltantes antes
    .venv/bin/python scripts/ime/run_ime_pipeline.py --download --force
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

IME_SCRIPTS_DIR = Path(__file__).resolve().parent
ROOT_DIR = IME_SCRIPTS_DIR.parent.parent


def run_step(script_name: str, extra_args: list[str] | None = None) -> None:
    script = IME_SCRIPTS_DIR / script_name
    cmd = [sys.executable, str(script), *(extra_args or [])]
    print(f"\n{'=' * 70}\n>>> Executando {script.relative_to(ROOT_DIR)}\n{'=' * 70}", flush=True)
    subprocess.run(cmd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline isolado de concluintes do IME (2000-2020) x OBM-U.")
    parser.add_argument("--download", action="store_true", help="Baixa os HTMLs oficiais do IME antes de processar.")
    parser.add_argument("--force", action="store_true", help="Força re-download dos HTMLs (requer --download).")
    args = parser.parse_args()

    if args.download:
        run_step("download_concluintes.py", ["--force"] if args.force else [])
    run_step("parse_concluintes.py")
    run_step("build_obm_ime_list.py")


if __name__ == "__main__":
    main()
