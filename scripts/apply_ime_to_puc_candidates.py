"""Consulta a lista isolada de premiados da OBM-U no IME para atualizar os candidatos PUC-Rio.

Este script NÃO acessa nem faz parsing das fontes brutas do IME; ele apenas consulta
a saída canônica produzida pelo processo isolado em:
- data/ime/processed/obm_university_ime_awardees.csv

E atualiza de forma idempotente:
- data/puc/obm_university_puc_rio_candidates.csv

Regras de atualização:
- Apenas utiliza registros do IME com Temporal_Check == 'COMPATIVEL_GRADUACAO'.
- Adiciona evidência no formato `IME Concluintes <Ano>: IME (<Especialidade>)` em
  `Other_Institution_Evidence` (sem duplicar se já existir).
- Se a classificação atual for `SEM_EVIDENCIA`, atualiza para `OUTRA_INSTITUICAO`.
- Se a classificação atual for `PUC_RIO_SEM_CONTRADICAO`, atualiza para `CONFLITO`.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
IME_OBM_CSV = ROOT_DIR / "data" / "ime" / "processed" / "obm_university_ime_awardees.csv"
PUC_CANDIDATES_CSV = ROOT_DIR / "data" / "puc" / "obm_university_puc_rio_candidates.csv"


def norm_key(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii").lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def format_ime_evidence(ime_row: dict[str, str]) -> str:
    yrs = ime_row["IME_Graduation_Years"].strip()
    specs = ime_row["IME_Specialties"].strip()
    if specs:
        return f"IME Concluintes {yrs}: IME ({specs})"
    return f"IME Concluintes {yrs}: IME"


def main() -> None:
    if not IME_OBM_CSV.exists():
        raise FileNotFoundError(
            f"Lista OBM-U x IME não encontrada: {IME_OBM_CSV}. "
            "Execute scripts/ime/run_ime_pipeline.py primeiro."
        )
    if not PUC_CANDIDATES_CSV.exists():
        raise FileNotFoundError(f"Arquivo de candidatos PUC-Rio não encontrado: {PUC_CANDIDATES_CSV}.")

    ime_df = pd.read_csv(IME_OBM_CSV, dtype=str).fillna("")
    puc_df = pd.read_csv(PUC_CANDIDATES_CSV, dtype=str, encoding="utf-8-sig").fillna("")

    ime_by_id: dict[str, dict[str, str]] = {}
    ime_by_norm: dict[str, dict[str, str]] = {}
    for _, r in ime_df.iterrows():
        if r["Temporal_Check"] != "COMPATIVEL_GRADUACAO":
            continue
        d = r.to_dict()
        ime_by_id[d["OBM_Person_id"]] = d
        ime_by_norm[d["Name_norm"]] = d

    before_counts = Counter(puc_df["Classification"])
    newly_resolved: list[tuple[str, str, str]] = []
    new_conflicts: list[tuple[str, str, str]] = []
    enriched_existing = 0

    for idx, r in puc_df.iterrows():
        pid = r["OBM_Person_id"]
        nk = norm_key(r["Person_canonical"])
        ime_hit = ime_by_id.get(pid) or ime_by_norm.get(nk)
        if not ime_hit:
            continue

        ev = format_ime_evidence(ime_hit)
        existing_ev = [e.strip() for e in r["Other_Institution_Evidence"].split(" | ") if e.strip()]
        if ev not in existing_ev:
            existing_ev.append(ev)
        puc_df.at[idx, "Other_Institution_Evidence"] = " | ".join(existing_ev)

        old_cls = r["Classification"]
        if old_cls == "SEM_EVIDENCIA":
            puc_df.at[idx, "Classification"] = "OUTRA_INSTITUICAO"
            newly_resolved.append((r["Person_canonical"], r["OBM_Years"], ev))
        elif old_cls == "PUC_RIO_SEM_CONTRADICAO":
            puc_df.at[idx, "Classification"] = "CONFLITO"
            new_conflicts.append((r["Person_canonical"], r["OBM_Years"], ev))
        else:
            enriched_existing += 1

    puc_df.to_csv(PUC_CANDIDATES_CSV, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_ALL)
    after_counts = Counter(puc_df["Classification"])

    print("=== ATUALIZAÇÃO DE CANDIDATOS PUC-RIO VIA LISTA OBM-U x IME ===")
    print(f"Fonte consultada: {IME_OBM_CSV.relative_to(ROOT_DIR)}")
    print(f"Arquivo atualizado: {PUC_CANDIDATES_CSV.relative_to(ROOT_DIR)}")
    print("\nContagem por classificação:")
    for cls in ["PUC_RIO_SEM_CONTRADICAO", "OUTRA_INSTITUICAO", "CONFLITO", "SEM_EVIDENCIA"]:
        print(f"  {cls:25s}: {before_counts.get(cls, 0):3d} -> {after_counts.get(cls, 0):3d}")
    print(f"\nRemovidos de SEM_EVIDENCIA (identificados como IME): {len(newly_resolved)}")
    print(f"Já eram OUTRA_INSTITUICAO/CONFLITO (enriquecidos com IME): {enriched_existing}")
    print(f"Novos conflitos com PUC-Rio: {len(new_conflicts)}")
    if newly_resolved:
        print("\nPessoas removidas de SEM_EVIDENCIA:")
        for name, yrs, ev in sorted(newly_resolved):
            print(f"  - {name} (OBM: {yrs}) -> {ev}")


if __name__ == "__main__":
    main()
