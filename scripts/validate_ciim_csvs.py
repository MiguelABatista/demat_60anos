"""Validador rigoroso ano a ano para os CSVs da CIIM (2009-2026)."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
BY_YEAR_DIR = ROOT_DIR / "data" / "ciim" / "processed" / "by_year"

VALID_PRIZES = {"Gold Special", "Gold", "Silver", "Bronze", "Honourable Mention", ""}
PROB_COLS = ["P1", "P2", "P3", "P4", "P5", "P6"]


def to_num(val: str) -> float | None:
    s = val.strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def validate_year(year: int) -> list[str]:
    path = BY_YEAR_DIR / f"ciim_results_{year}.csv"
    issues: list[str] = []
    if not path.exists():
        return [f"ARQUIVO AUSENTE: {path}"]

    df = pd.read_csv(path, dtype=str).fillna("")
    if len(df) == 0:
        return ["CSV VAZIO (0 linhas)"]

    # 1. Nomes vazios ou suspeitos
    empty_name = df[df["Full name"].str.strip() == ""]
    if len(empty_name):
        issues.append(f"{len(empty_name)} linhas com Full name vazio")

    suspect = df[df["Full name"].str.contains(r"\d|medalla|premio|total|resultado|cuadro", case=False, regex=True)]
    if len(suspect):
        issues.append(f"{len(suspect)} nomes suspeitos: {suspect['Full name'].tolist()[:5]}")

    # 2. Duplicatas
    dups = df[df.duplicated(subset=["Full name"], keep=False)]
    if len(dups):
        issues.append(f"{len(dups)} linhas com Full name duplicado: {dups['Full name'].unique().tolist()[:5]}")

    # 3. País vazio (exceto participantes individuais sem instituição/país informados no PDF oficial)
    empty_co = df[(df["Country"].str.strip() == "") & (df["University"].str.strip().str.lower() != "individual")]
    if len(empty_co):
        samples = empty_co[["Full name", "University", "Prize"]].head(5).to_dict("records")
        issues.append(f"{len(empty_co)} linhas com Country vazio: {samples}")

    # 4. Prêmios não canônicos
    unknown_p = sorted(set(df["Prize"].unique()) - VALID_PRIZES)
    if unknown_p:
        issues.append(f"Prizes não canônicos: {unknown_p}")

    # 5. Validade numérica e aritmética P1..P6 == Total
    for col in [*PROB_COLS, "Total"]:
        bad = []
        for idx, v in enumerate(df[col]):
            s = v.strip()
            if not s or (col in PROB_COLS and s.upper() == "NP"):
                continue
            n = to_num(s)
            if n is None or (col in PROB_COLS and not (0 <= n <= 10)) or (col == "Total" and not (0 <= n <= 60)):
                bad.append((idx, df.loc[idx, "Full name"], s))
        if bad:
            issues.append(f"Coluna {col} com valores inválidos ({len(bad)}): {bad[:5]}")

    mismatches = []
    for idx, r in df.iterrows():
        pvals = [to_num(r[c]) for c in PROB_COLS]
        tot = to_num(r["Total"])
        if any(v is not None for v in pvals) and tot is not None:
            s = sum(v for v in pvals if v is not None)
            if abs(s - tot) > 1e-6:
                mismatches.append((r["Full name"], s, tot))
    if mismatches:
        issues.append(f"Total != sum(P1..P6) em {len(mismatches)} linhas: {mismatches[:5]}")

    return issues


def main() -> None:
    total = 0
    bad_years = 0
    for year in range(2009, 2027):
        path = BY_YEAR_DIR / f"ciim_results_{year}.csv"
        df = pd.read_csv(path, dtype=str).fillna("") if path.exists() else pd.DataFrame()
        total += len(df)
        issues = validate_year(year)
        pc = df["Prize"].value_counts().to_dict() if len(df) else {}
        g = pc.get("Gold Special", 0) + pc.get("Gold", 0)
        s = pc.get("Silver", 0)
        b = pc.get("Bronze", 0)
        hm = pc.get("Honourable Mention", 0)
        status = "OK" if not issues else f"ATENÇÃO ({len(issues)} alertas)"
        if issues:
            bad_years += 1
        print(f"{year} | n={len(df):3d} | O={g:2d} P={s:2d} B={b:2d} MH={hm:2d} | {status}")
        for iss in issues:
            print(f"    ! {iss}")
    print(f"\nResumo CIIM: {18 - bad_years}/18 anos limpos | {bad_years} com alertas | Total={total:,} participantes")
    if bad_years:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
