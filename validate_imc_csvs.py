"""Validador rigoroso ano a ano para os CSVs da IMC (1994-2026)."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

OUTPUT_DIR = Path("imc_results")

VALID_PRIZES = {
    "Grand Grand First Prize",
    "Grand First Prize",
    "First Prize",
    "Upper Second Prize",
    "Second Prize",
    "Third Prize",
    "Honourable Mention",
    "Special Mention",
    "Certificate",
    "Withdrawn",
    "Disqualified",
}

D1_COLS = [f"D1_P{i}" for i in range(1, 7)]
D2_COLS = [f"D2_P{i}" for i in range(1, 7)]
NUM_COLS = ["Code_D1", *D1_COLS, "Day1", "Code_D2", *D2_COLS, "Day2", "Sum"]


def to_num(val: str) -> float | None:
    s = val.strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def validate_year(year: int) -> list[str]:
    path = OUTPUT_DIR / f"imc_results_{year}.csv"
    issues: list[str] = []
    if not path.exists():
        return [f"ARQUIVO AUSENTE: {path}"]

    df = pd.read_csv(path, dtype=str).fillna("")
    n = len(df)
    if n == 0:
        return ["CSV VAZIO (0 linhas)"]

    # 1. Campos essenciais
    empty_name = df[df["Full name"].str.strip() == ""]
    if len(empty_name):
        issues.append(f"{len(empty_name)} linhas com Full name vazio (idx={empty_name.index.tolist()[:5]})")

    suspect_name = df[df["Full name"].str.contains(r"\b(?:average|results|final|imc|sheet|page)\b|\d", case=False, regex=True)]
    if len(suspect_name):
        samples = suspect_name[["Pos", "Full name", "University"]].head(5).to_dict("records")
        issues.append(f"{len(suspect_name)} nomes suspeitos: {samples}")

    empty_univ = df[df["University"].str.strip() == ""]
    if len(empty_univ):
        samples = empty_univ[["Pos", "Full name", "Sum", "Prize"]].head(5).to_dict("records")
        issues.append(f"{len(empty_univ)} linhas com University vazio: {samples}")

    # 2. Prize
    empty_prize = df[df["Prize"].str.strip() == ""]
    if len(empty_prize):
        samples = empty_prize[["Pos", "Full name", "Sum"]].head(5).to_dict("records")
        issues.append(f"{len(empty_prize)} linhas com Prize vazio: {samples}")

    unknown_prizes = sorted(set(df["Prize"].unique()) - VALID_PRIZES - {""})
    if unknown_prizes:
        issues.append(f"Prizes não canônicos: {unknown_prizes}")

    # 3. Colunas numéricas (não devem conter lixo textual exceto disqualified/withdrawn)
    for col in NUM_COLS:
        bad_rows = []
        for idx, val in enumerate(df[col]):
            s = val.strip()
            if not s:
                continue
            if s.lower() in {"disqualified", "withdrawn", "abs", "dns"}:
                continue
            if to_num(s) is None:
                bad_rows.append((idx, df.loc[idx, "Pos"], df.loc[idx, "Full name"], s))
        if bad_rows:
            issues.append(f"Coluna {col} com {len(bad_rows)} valores não-numéricos: {bad_rows[:5]}")

    # 4. Integridade aritmética
    has_d1_probs = any(df[c].str.strip().ne("").any() for c in D1_COLS)
    has_d2_probs = any(df[c].str.strip().ne("").any() for c in D2_COLS)
    has_day1 = df["Day1"].str.strip().ne("").any()
    has_day2 = df["Day2"].str.strip().ne("").any()
    has_sum = df["Sum"].str.strip().ne("").any()

    d1_mismatch = []
    d2_mismatch = []
    sum_mismatch = []

    for idx, r in df.iterrows():
        if r["Prize"] in {"Withdrawn", "Disqualified"} or r["Sum"].lower() in {"disqualified", "withdrawn"}:
            continue
        d1_vals = [to_num(r[c]) for c in D1_COLS if to_num(r[c]) is not None]
        d2_vals = [to_num(r[c]) for c in D2_COLS if to_num(r[c]) is not None]
        day1 = to_num(r["Day1"])
        day2 = to_num(r["Day2"])
        tot = to_num(r["Sum"])

        if has_d1_probs and has_day1 and day1 is not None:
            if abs(sum(d1_vals) - day1) > 1e-6:
                d1_mismatch.append((r["Pos"], r["Full name"], sum(d1_vals), day1))
        if has_d2_probs and has_day2 and day2 is not None:
            if abs(sum(d2_vals) - day2) > 1e-6:
                d2_mismatch.append((r["Pos"], r["Full name"], sum(d2_vals), day2))
        if has_day1 and has_day2 and has_sum and tot is not None:
            exp = (day1 or 0.0) + (day2 or 0.0)
            if abs(exp - tot) > 1e-6:
                sum_mismatch.append((r["Pos"], r["Full name"], day1, day2, tot))
        elif has_d1_probs and has_d2_probs and not has_day1 and has_sum and tot is not None:
            exp = sum(d1_vals) + sum(d2_vals)
            if abs(exp - tot) > 1e-6:
                sum_mismatch.append((r["Pos"], r["Full name"], exp, tot))

    if d1_mismatch:
        issues.append(f"Day1 != sum(D1_P*) em {len(d1_mismatch)} linhas: {d1_mismatch[:5]}")
    if d2_mismatch:
        issues.append(f"Day2 != sum(D2_P*) em {len(d2_mismatch)} linhas: {d2_mismatch[:5]}")
    if sum_mismatch:
        issues.append(f"Sum != Day1+Day2 em {len(sum_mismatch)} linhas: {sum_mismatch[:5]}")

    # 5. Monotonicidade de Sum (para linhas ranqueadas)
    if has_sum:
        prev = None
        non_mono = []
        for idx, r in df.iterrows():
            if r["Prize"] in {"Withdrawn", "Disqualified"}:
                continue
            tot = to_num(r["Sum"])
            if tot is None:
                continue
            if prev is not None and tot > prev + 1e-6:
                non_mono.append((r["Pos"], r["Full name"], prev, tot))
            prev = tot
        if non_mono:
            issues.append(f"Sum fora de ordem decrescente em {len(non_mono)} pontos: {non_mono[:5]}")

    # 6. Continuidade de Pos (quando Pos existe)
    if year >= 1999:
        pos_list = df["Pos"].tolist()
        # Checar se todas as linhas (exceto withdrawn) têm Pos
        missing_pos = [
            (idx, df.loc[idx, "Full name"], df.loc[idx, "Prize"])
            for idx, p in enumerate(pos_list)
            if not p and df.loc[idx, "Prize"] != "Withdrawn"
        ]
        if missing_pos:
            issues.append(f"{len(missing_pos)} linhas sem Pos: {missing_pos[:5]}")
        # Verificar se o último número de Pos bate com contagem ranqueada
        ranked = [p for p in pos_list if p]
        if ranked:
            # Extrair maior número do último Pos (ex: "442–448" -> 448)
            nums_last = [int(x) for x in re.findall(r"\d+", ranked[-1])]
            nums_first = [int(x) for x in re.findall(r"\d+", ranked[0])]
            if nums_first and nums_first[0] != 1:
                issues.append(f"Primeiro Pos não começa em 1: {ranked[0]!r}")
            if nums_last and nums_last[-1] != len(ranked):
                issues.append(f"Último Pos ({ranked[-1]!r}) != nº de ranqueados ({len(ranked)})")

    return issues


def main() -> None:
    total_rows = 0
    years_with_issues = 0
    for year in range(1994, 2027):
        path = OUTPUT_DIR / f"imc_results_{year}.csv"
        df = pd.read_csv(path, dtype=str).fillna("") if path.exists() else pd.DataFrame()
        total_rows += len(df)
        issues = validate_year(year)
        prizes_summary = df["Prize"].value_counts().to_dict() if len(df) else {}
        status = "OK" if not issues else f"ATENÇÃO ({len(issues)} alertas)"
        if issues:
            years_with_issues += 1
        print(f"{year} | n={len(df):4d} | {status}")
        if issues:
            for iss in issues:
                print(f"    ! {iss}")
    print(f"\nResumo: {33 - years_with_issues}/33 anos limpos | {years_with_issues} com alertas | Total={total_rows:,} participantes")


if __name__ == "__main__":
    main()
