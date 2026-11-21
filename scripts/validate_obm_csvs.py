"""Validador rigoroso ano a ano para os CSVs da OBM (1979-2025)."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
BY_YEAR_DIR = ROOT_DIR / "data" / "obm" / "processed" / "by_year"

VALID_PRIZES = {
    "Ouro Especial",
    "Ouro",
    "Prata",
    "Bronze",
    "Menção Honrosa",
    "Destaque Regional",
    "Premiado",
    "1º Prêmio",
    "2º Prêmio",
    "3º Prêmio",
    "4º Prêmio",
    "5º Prêmio",
    "6º Prêmio",
    "7º Prêmio",
}

VALID_UFS = {
    "", "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT",
    "PA", "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO",
}


def expected_levels(year: int) -> set[str]:
    if year <= 1990:
        return {"Único"}
    if year <= 1997:
        return {"Júnior", "Sênior"}
    if year <= 2000:
        return {"Nível 1", "Nível 2", "Nível 3"}
    return {"Nível 1", "Nível 2", "Nível 3", "Nível Universitário"}


def validate_year(year: int) -> list[str]:
    path = BY_YEAR_DIR / f"obm_results_{year}.csv"
    issues: list[str] = []
    if not path.exists():
        return [f"ARQUIVO AUSENTE: {path}"]

    df = pd.read_csv(path, dtype=str).fillna("")
    if len(df) == 0:
        return ["CSV VAZIO (0 linhas)"]

    # 1. Níveis esperados
    got_levels = set(df["Level"].unique())
    exp_levels = expected_levels(year)
    if got_levels != exp_levels:
        issues.append(f"Níveis inesperados: obtido={sorted(got_levels)}, esperado={sorted(exp_levels)}")

    # 2. Nomes vazios ou suspeitos
    empty_name = df[df["Full name"].str.strip() == ""]
    if len(empty_name):
        issues.append(f"{len(empty_name)} linhas com Full name vazio")

    suspect = df[df["Full name"].str.contains(r"\d|[<>]|/[a-zA-Z]+>|\b(?:pr[eê]mio|pontos|cidade|ouro|prata|bronze)\b", case=False, regex=True)]
    if len(suspect):
        issues.append(f"{len(suspect)} nomes suspeitos: {suspect['Full name'].tolist()[:5]}")

    # 3. Duplicatas exatas no mesmo ano e nível
    dups = df[df.duplicated(subset=["Level", "Full name"], keep=False)]
    if len(dups):
        issues.append(
            f"{len(dups)} duplicatas no mesmo nível: "
            + str(dups[["Level", "Full name", "City", "Prize"]].to_dict("records")[:5])
        )

    # 4. Prêmios canônicos
    unknown_p = sorted(set(df["Prize"].unique()) - VALID_PRIZES)
    if unknown_p:
        issues.append(f"Prizes não canônicos: {unknown_p}")
    empty_p = df[df["Prize"].str.strip() == ""]
    if len(empty_p):
        issues.append(f"{len(empty_p)} linhas sem Prize")

    # 5. UFs válidas (a partir de 1987 a OBM publica Cidade - Estado; exceto 1 caso vazio '–' em 1991)
    bad_uf = sorted(set(df["State"].unique()) - VALID_UFS)
    if bad_uf:
        issues.append(f"UFs inválidas: {bad_uf}")
    if year >= 1987:
        missing_uf = df[(df["State"] == "") & (df["City_State_raw"].str.strip().isin({"", "-", "–", "—"}) == False)]
        if len(missing_uf):
            issues.append(f"{len(missing_uf)} linhas com Cidade preenchida mas UF vazia: {missing_uf[['Full name', 'City_State_raw']].head(5).to_dict('records')}")

    # 6. Pontuação (a partir de 1998 todos os premiados têm Points numérico)
    if year >= 1998:
        bad_pts = df[~df["Points"].str.fullmatch(r"\d+")]
        if len(bad_pts):
            issues.append(f"{len(bad_pts)} linhas com Points não numérico: {bad_pts[['Full name', 'Points']].head(5).to_dict('records')}")

    return issues


def main() -> None:
    total = 0
    bad_years = 0
    for year in range(1979, 2026):
        path = BY_YEAR_DIR / f"obm_results_{year}.csv"
        df = pd.read_csv(path, dtype=str).fillna("") if path.exists() else pd.DataFrame()
        total += len(df)
        issues = validate_year(year)
        n_u = int((df["Level"] == "Nível Universitário").sum()) if len(df) else 0
        status = "OK" if not issues else f"ATENÇÃO ({len(issues)} alertas)"
        if issues:
            bad_years += 1
        print(f"{year} ({year - 1978:2d}ª) | total={len(df):3d} | Univ={n_u:2d} | {status}")
        for iss in issues:
            print(f"    ! {iss}")

    print(f"\nResumo OBM: {47 - bad_years}/47 anos limpos | {bad_years} com alertas | Total={total:,} premiados")
    if bad_years:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
