"""Executa o pipeline completo de coleta, extração, validação e normalização (IMC, CIIM e OBM).

Uso:
    .venv/bin/python run_pipeline.py                       # roda IMC + CIIM + OBM a partir do cache local
    .venv/bin/python run_pipeline.py --competition imc     # roda somente IMC (1994-2026)
    .venv/bin/python run_pipeline.py --competition ciim    # roda somente CIIM (2009-2026)
    .venv/bin/python run_pipeline.py --competition obm     # roda somente OBM (1979-2025)
    .venv/bin/python run_pipeline.py --download            # também baixa fontes oficiais faltantes
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


def run_imc(download: bool) -> None:
    if download:
        run_step("download_imc_pdfs.py")
    run_step("build_imc_csvs.py")
    run_step("validate_imc_csvs.py")
    run_step("filter_brazil.py")


def run_ciim(download: bool) -> None:
    if download:
        run_step("download_ciim.py")
    run_step("build_ciim_csvs.py")
    run_step("validate_ciim_csvs.py")
    run_step("filter_ciim_brazil.py")


def run_obm(download: bool) -> None:
    if download:
        run_step("download_obm.py")
    run_step("build_obm_csvs.py")
    run_step("validate_obm_csvs.py")
    run_step("normalize_obm.py")


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipelines de resultados IMC (1994-2026), CIIM (2009-2026) e OBM (1979-2025)")
    parser.add_argument(
        "--competition",
        choices=["all", "imc", "ciim", "obm"],
        default="all",
        help="Competição a processar (padrão: all).",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Baixa fontes oficiais faltantes antes de gerar os CSVs.",
    )
    args = parser.parse_args()

    if args.competition in {"all", "imc"}:
        run_imc(args.download)
    if args.competition in {"all", "ciim"}:
        run_ciim(args.download)
    if args.competition in {"all", "obm"}:
        run_obm(args.download)


if __name__ == "__main__":
    main()
