"""Executa o pipeline completo de coleta, extração, validação e filtro de brasileiros da IMC.

Uso:
    .venv/bin/python run_pipeline.py            # gera e valida todos os CSVs a partir do cache local
    .venv/bin/python run_pipeline.py --download # também baixa PDFs faltantes do site da IMC
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = ROOT_DIR / "scripts"


def run_step(script_name: str) -> None:
    script = SCRIPTS_DIR / script_name
    print(f"\n{'=' * 70}\n>>> Executando {script.relative_to(ROOT_DIR)}\n{'=' * 70}", flush=True)
    subprocess.run([sys.executable, str(script)], check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline IMC (1994-2026)")
    parser.add_argument(
        "--download",
        action="store_true",
        help="Baixa PDFs oficiais faltantes de imc-math.org.uk antes de gerar os CSVs.",
    )
    args = parser.parse_args()

    if args.download:
        run_step("download_imc_pdfs.py")
    run_step("build_imc_csvs.py")
    run_step("validate_imc_csvs.py")
    run_step("filter_brazil.py")


if __name__ == "__main__":
    main()
