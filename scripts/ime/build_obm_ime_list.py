"""Cruza concluintes do IME (2000-2020) com os premiados do Nível Universitário da OBM (2001-2025).

Este processo é isolado: apenas lê os CSVs processados do IME e da OBM-U e gera
uma tabela canônica de premiados da OBM-U encontrados nas listas de concluintes do IME,
para que outros processos do repositório consultem posteriormente.

Entradas:
- data/ime/processed/ime_concluintes.csv
- data/obm/processed/university/obm_university_people.csv

Saída:
- data/ime/processed/obm_university_ime_awardees.csv
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
IME_CONCLUINTES_CSV = ROOT_DIR / "data" / "ime" / "processed" / "ime_concluintes.csv"
OBM_PEOPLE_CSV = ROOT_DIR / "data" / "obm" / "processed" / "university" / "obm_university_people.csv"
OUT_CSV = ROOT_DIR / "data" / "ime" / "processed" / "obm_university_ime_awardees.csv"

# Equivalências auditadas entre nome normalizado na OBM-U e nome normalizado na lista do IME
# (chave OBM norm_key -> (chave IME norm_key, nota de auditoria))
AUDITED_OBM_IME_ALIASES: dict[str, tuple[str, str]] = {
    "alexandre azevedo cesar": (
        "alexandre azevedo cezar",
        "Grafia César/Cezár (também registrado como IME na CIIM 2011 e 2012)",
    ),
    "antonia taline de souza mendonca": (
        "antonia talita de souza mendonca",
        "Grafia Taline/Talita (confirmada como aluna do 2º ano do CFG/IME em 2007 em publicação oficial do EB)",
    ),
    "antonio carlos maldonado s alonso munhoz": (
        "antonio carlos maldonado silveira alonso munhoz",
        "Inicial 'S.' na OBM corresponde a 'Silveira' na lista de concluintes do IME 2008",
    ),
    "pedro kenzo de alencar ohi": (
        "pedro kenzo alencar ohi",
        "Omissão da preposição 'de' na lista de concluintes do IME 2014",
    ),
    "thomas rincon reis": (
        "thomas ricon reis",
        "Typo 'RICON' na lista de concluintes do IME 2017 (também registrado como IME na IMC/CIIM 2014-2015)",
    ),
    "victor feitosa e carvalho souza": (
        "victor feitosa de carvalho souza",
        "Preposição 'e' vs 'de' (confirmado concluinte de Engenharia de Computação do IME em 2017)",
    ),
}


def norm_key(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii").lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def main() -> None:
    if not IME_CONCLUINTES_CSV.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {IME_CONCLUINTES_CSV}. Execute scripts/ime/parse_concluintes.py primeiro."
        )
    if not OBM_PEOPLE_CSV.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {OBM_PEOPLE_CSV}.")

    ime_df = pd.read_csv(IME_CONCLUINTES_CSV, dtype=str).fillna("")
    obm_df = pd.read_csv(OBM_PEOPLE_CSV, dtype=str).fillna("")

    ime_by_norm: dict[str, list[dict[str, str]]] = {}
    for _, r in ime_df.iterrows():
        ime_by_norm.setdefault(r["Name_norm"], []).append(r.to_dict())

    matched_rows: list[dict[str, object]] = []
    for _, r in obm_df.iterrows():
        canon = r["Person_canonical"]
        variants = [v.strip() for v in r["Name_variants"].split(" | ") if v.strip()]
        candidate_keys = list(dict.fromkeys([norm_key(canon)] + [norm_key(v) for v in variants]))

        hits: list[dict[str, str]] | None = None
        match_type = ""
        match_note = ""

        # 1. Correspondência exata por nome normalizado (canônico ou variante da OBM)
        for k in candidate_keys:
            if k in ime_by_norm:
                hits = ime_by_norm[k]
                match_type = "EXACT"
                match_note = "Correspondência exata de nome normalizado"
                break

        # 2. Equivalência auditada
        if hits is None:
            for k in candidate_keys:
                if k in AUDITED_OBM_IME_ALIASES:
                    ime_key, note = AUDITED_OBM_IME_ALIASES[k]
                    if ime_key in ime_by_norm:
                        hits = ime_by_norm[ime_key]
                        match_type = "AUDITED_ALIAS"
                        match_note = note
                        break

        if not hits:
            continue

        obm_years = [int(y.strip()) for y in r["Years"].split(",") if y.strip()]
        ime_years = sorted({int(h["Year"]) for h in hits})
        deltas = [iy - oy for iy in ime_years for oy in obm_years]
        delta_min, delta_max = min(deltas), max(deltas)

        # CFG do IME dura 5 anos; delta entre 0 e 5 cobre graduação (e entrada imediatamente após OBM-U)
        if 0 <= delta_min and delta_max <= 5:
            temporal_check = "COMPATIVEL_GRADUACAO"
        else:
            temporal_check = "FORA_JANELA_0_5"

        ime_specs = list(dict.fromkeys(h["Specialty"] for h in hits if h["Specialty"]))
        ime_ranks = list(dict.fromkeys(h["Rank"] for h in hits if h["Rank"]))
        ime_names = list(dict.fromkeys(h["Full_name"] for h in hits if h["Full_name"]))
        source_urls = list(dict.fromkeys(h["Source_url"] for h in hits if h["Source_url"]))

        matched_rows.append(
            {
                "OBM_Person_id": r["Person_id"],
                "Person_canonical": canon,
                "Name_norm": norm_key(canon),
                "OBM_Awards_total": int(r["Awards_total"]),
                "OBM_Years": r["Years"],
                "OBM_States": r["States"],
                "OBM_Cities": r["Cities"],
                "IME_Graduation_Years": ", ".join(str(y) for y in ime_years),
                "IME_Specialties": " | ".join(ime_specs),
                "IME_Ranks": " | ".join(ime_ranks),
                "IME_Names_raw": " | ".join(ime_names),
                "Year_Delta_Min": delta_min,
                "Year_Delta_Max": delta_max,
                "Temporal_Check": temporal_check,
                "Match_type": match_type,
                "Match_note": match_note,
                "Source_URLs": " | ".join(source_urls),
            }
        )

    out_df = pd.DataFrame(matched_rows).sort_values(
        ["IME_Graduation_Years", "Person_canonical"], ascending=[True, True]
    )
    out_df.to_csv(OUT_CSV, index=False, encoding="utf-8")

    exact_n = int((out_df["Match_type"] == "EXACT").sum())
    alias_n = int((out_df["Match_type"] == "AUDITED_ALIAS").sum())
    compat_n = int((out_df["Temporal_Check"] == "COMPATIVEL_GRADUACAO").sum())

    print("=== LISTA DE PREMIADOS OBM-U NO IME GERADA ===")
    print(f"Total de premiados OBM-U encontrados no IME: {len(out_df)}")
    print(f"  - EXACT:          {exact_n}")
    print(f"  - AUDITED_ALIAS:  {alias_n}")
    print(f"  - Compatível com janela de graduação (0..5 anos): {compat_n}/{len(out_df)}")
    print(f"Arquivo gerado: {OUT_CSV.relative_to(ROOT_DIR)}")


if __name__ == "__main__":
    main()
