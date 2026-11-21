"""Filtra e normaliza todos os participantes e universidades brasileiras na CIIM (2009-2026).

Lida com:
1. Variações de grafia, sigla, idioma, numeração de equipe e typos nas universidades
   (ex.: IME 1 / IME2 / Instituto Militar de Ingeniería -> IME; PUC1/RJ / Pontifice... -> PUC-Rio;
   EMAP/FGV / FGV Rio -> FGV; EST/UEA / UEA -> UEA; IME/USP / USP - São Carlos -> USP).
2. Variações de nome nas pessoas (acentos, maiúsculas, nomes abreviados em 2014/2023,
   nomes invertidos, truncamento em 2026 e typos como Babtista/Miyasaki).

Saídas em data/ciim/processed/brazil/:
- ciim_brazil_participations.csv (todas as participações brasileiras, 2009-2026)
- ciim_brazil_people.csv         (resumo consolidado: 1 linha por pessoa única)
- ciim_brazil_universities.csv   (resumo consolidado: 1 linha por instituição brasileira)
- ciim_brazil_by_year.csv        (resumo anual de participações e premiações)
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
INPUT_CSV = ROOT_DIR / "data" / "ciim" / "processed" / "ciim_results_all_years.csv"
OUT_DIR = ROOT_DIR / "data" / "ciim" / "processed" / "brazil"

# Regras de normalização de instituições brasileiras na CIIM
# Ordem importa: padrões mais específicos primeiro (ex.: IME-USP antes de IME; OBM/ITA antes de OBM).
BR_UNIVERSITY_RULES: list[tuple[str, str, str]] = [
    (r"\bime.?usp\b|\busp\b|universidade? de sao paulo", "USP", "Universidade de São Paulo (USP)"),
    (r"\bita\b|tecnol.?g.*aeronaut", "ITA", "Instituto Tecnológico de Aeronáutica (ITA)"),
    (r"\bime\d*\b|instituto militar de eng|instituto militar de ingenier", "IME", "Instituto Militar de Engenharia (IME)"),
    (r"puc\d*\s*(rio|rj)|\bobm\s+puc\b|pontific\w*\s+universidad\w*\s+catolic\w*", "PUC-Rio", "Pontifícia Universidade Católica do Rio de Janeiro (PUC-Rio)"),
    (r"\bfgv\b|\bemap\b|getulio vargas", "FGV", "Fundação Getulio Vargas (FGV)"),
    (r"\bunicamp\b|estadual de campinas", "UNICAMP", "Universidade Estadual de Campinas (UNICAMP)"),
    (r"\bufmg\b|federal de minas gerais", "UFMG", "Universidade Federal de Minas Gerais (UFMG)"),
    (r"\bufal\b|federal de alagoas", "UFAL", "Universidade Federal de Alagoas (UFAL)"),
    (r"\buea\b|est/uea|estadual do amazonas", "UEA", "Universidade do Estado do Amazonas (UEA)"),
    (r"\bimpa\b", "IMPA", "Instituto de Matemática Pura e Aplicada (IMPA)"),
    (r"\bufc\b|federal do cear", "UFC", "Universidade Federal do Ceará (UFC)"),
    (r"\bufcg\b|federal de campina grande", "UFCG", "Universidade Federal de Campina Grande (UFCG)"),
    (r"\buece\b|estadual do cear", "UECE", "Universidade Estadual do Ceará (UECE)"),
    (r"\bufpe\b|federal.*pernambuco", "UFPE", "Universidade Federal de Pernambuco (UFPE)"),
    (r"\bobm\b|olimp[ií]adas?\s+brasil|time brasil|^brasil$", "OBM", "Olimpíada Brasileira de Matemática (OBM)"),
]

OBM_TEAM_RE = re.compile(r"\bobm\b|olimp[ií]adas?\s+brasil|time brasil|^brasil$", re.I)

# Equivalências auditadas de nomes de pessoas (chave ASCII normalizada -> nome canônico)
# Cada entrada foi verificada individualmente por ano, instituição e histórico (incluindo cruzamento com a IMC).
PERSON_ALIAS_MAP: dict[str, str] = {
    # Acentos / maiúsculas / grafia
    "alexandre azevedo cezar": "Alexandre Azevedo Cézar",
    "andre yuji hisatsuga": "André Yuji Hisatsuga",
    "andrey jhen shan chen": "Andrey Jhen Shan Chen",
    "caio augusto costa": "Caio Augusto de Carvalho Costa",
    "caio augusto de carvalho costa": "Caio Augusto de Carvalho Costa",
    "felipe goncalves assis": "Felipe Gonçalves Assis",
    "joao vitor tomaz alves ferreira": "João Vítor Tomaz Alves Ferreira",
    "lucas da silva reis": "Lucas da Silva Reis",
    "luis felipe pestana giglio": "Luís Felipe Pestana Giglio",
    "rafael filipe dos santos": "Rafael Filipe dos Santos",
    "ramyro correa aquines": "Ramyro Corrêa Aquines",
    # Nomes invertidos (sobrenome antes do nome no PDF oficial)
    "soares sousa felipi adenildo": "Felipi Adenildo Soares Sousa",
    "felipi adenildo soares sousa": "Felipi Adenildo Soares Sousa",
    "fraga ramires luan arjuna": "Luan Arjuna Fraga Ramires",
    "luan arjuna fraga ramires": "Luan Arjuna Fraga Ramires",
    # Typos / truncamentos oficiais
    "joao babtista de paula e silva": "João Baptista de Paula e Silva",
    "joao baptista de paula e silva": "João Baptista de Paula e Silva",
    "rafael kazuhiro miyasaki": "Rafael Kazuhiro Miyazaki",
    "rafael kazuhiro miyazaki": "Rafael Kazuhiro Miyazaki",
    "thiago landim souza leao": "Thiago Landim de Souza Leão",
    "thiago landim de souza leao": "Thiago Landim de Souza Leão",
    "joao marcelo": "João Marcelo Ribeiro Monteiro de Carvalho",
    "joao marcelo ribeiro monteiro de car": "João Marcelo Ribeiro Monteiro de Carvalho",
    "joao marcelo ribeiro monteiro de carvalho": "João Marcelo Ribeiro Monteiro de Carvalho",
    # Abreviações de nomes (especialmente CIIM 2014, 2021, 2023)
    "arthur vieira": "Arthur Moreira Martins Vieira",
    "arthur moreira martins vieira": "Arthur Moreira Martins Vieira",
    "breno marot": "Breno Azevedo Marot",
    "breno azevedo marot": "Breno Azevedo Marot",
    "george lucas": "George Lucas Diniz Alencar",
    "george lucas diniz alencar": "George Lucas Diniz Alencar",
    "hazael jumonji": "Hazael Soledade de Araujo Jumonji",
    "hazael soledade de araujo jumonji": "Hazael Soledade de Araujo Jumonji",
    "joao arthur": "João Arthur Marques Linhares",
    "joao arthur marques": "João Arthur Marques Linhares",
    "joao arthur marques linhares": "João Arthur Marques Linhares",
    "lael lima": "Lael Viana Lima",
    "lael viana lima": "Lael Viana Lima",
    "lucas herlin": "Lucas de Moura Herlin",
    "lucas de moura herlin": "Lucas de Moura Herlin",
    "luize d urso": "Luíze Mello D'Urso Vianna",
    "luize mello d urso vianna": "Luíze Mello D'Urso Vianna",
    "matheus assuncao": "Matheus Leal Assunção",
    "matheus leal assuncao": "Matheus Leal Assunção",
    "matheus secco": "Matheus Secco Torres da Silva",
    "matheus secco torres da silva": "Matheus Secco Torres da Silva",
    "miguel batista": "Miguel dos Anjos Batista",
    "miguel dos anjos batista": "Miguel dos Anjos Batista",
    "pedro mariano": "Pedro Mariano Viana Neto",
    "pedro mariano viana neto": "Pedro Mariano Viana Neto",
    "roberto pereira": "Roberto Pereira Garcia Junior",
    "roberto pereira garcia junior": "Roberto Pereira Garcia Junior",
    "thiago ribeiro": "Thiago Ribeiro Tergolino",  # 2014 IME (confirmado distinto de Thiago Ribeiro Ramos - ITA)
    "thiago ribeiro tergolino": "Thiago Ribeiro Tergolino",
    "thomas rincon": "Thomas Rincon Reis",
    "thomas rincon reis": "Thomas Rincon Reis",
}

PRIZE_ORDER = {
    "Gold Special": 1,
    "Gold": 2,
    "Silver": 3,
    "Bronze": 4,
    "Honourable Mention": 5,
    "": 6,
}


def strip_accents(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")


def norm_key(s: str) -> str:
    s = strip_accents(str(s)).lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def slug_id(name: str) -> str:
    return re.sub(r"\s+", "_", norm_key(name))


def canonicalize_university(raw_univ: str) -> tuple[str, str, bool]:
    s = str(raw_univ).strip()
    if not s:
        return ("Não informado", "Universidade não informada na fonte oficial (2026)", False)
    k = norm_key(s)
    is_obm = bool(OBM_TEAM_RE.search(k))
    for pattern, canon, full_name in BR_UNIVERSITY_RULES:
        if re.search(pattern, k):
            return (canon, full_name, is_obm)
    return (s, s, is_obm)


def canonicalize_person(raw_name: str, fallback_best: dict[str, str]) -> str:
    cleaned = re.sub(r"\s+", " ", str(raw_name)).strip()
    k = norm_key(cleaned)
    if k in PERSON_ALIAS_MAP:
        return PERSON_ALIAS_MAP[k]
    return fallback_best.get(k, cleaned)


def choose_best_spelling(variants: list[str]) -> str:
    """Entre grafias equivalentes em ASCII, escolhe a com mais acentos e capitalização mais limpa."""
    def score(s: str) -> tuple[int, int, int, int]:
        not_all_caps = 1 if (s != s.upper() and s != s.lower()) else 0
        accents = sum(1 for ch in s if ord(ch) > 127)
        no_weird_mid_caps = 0 if re.search(r"[a-z][A-Z]", s) else 1
        return (not_all_caps, no_weird_mid_caps, accents, len(s))
    return max(variants, key=score)


def best_prize(prizes: list[str]) -> str:
    return min(prizes, key=lambda p: PRIZE_ORDER.get(p, 99))


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(INPUT_CSV, dtype=str).fillna("")
    df["Year_int"] = df["Year"].astype(int)

    # Filtra participações brasileiras
    br = df[df["Country"] == "Brasil"].copy()

    # Melhor grafia automática para nomes com mesma chave ASCII não listados no alias map
    ascii_groups: dict[str, list[str]] = {}
    for raw_name in br["Full name"]:
        cleaned = re.sub(r"\s+", " ", raw_name).strip()
        ascii_groups.setdefault(norm_key(cleaned), []).append(cleaned)
    fallback_best = {k: choose_best_spelling(vs) for k, vs in ascii_groups.items()}

    # Aplica normalização de universidades e pessoas
    univ_info = br["University"].apply(canonicalize_university)
    br["University_canonical"] = [x[0] for x in univ_info]
    br["University_full_name"] = [x[1] for x in univ_info]
    br["OBM_team"] = [x[2] for x in univ_info]
    br["Person_canonical"] = br["Full name"].apply(lambda n: canonicalize_person(n, fallback_best))
    br["Person_id"] = br["Person_canonical"].apply(slug_id)

    # Verificação de segurança: nenhum Person_id pode aparecer 2x no mesmo ano!
    same_year_dups = br[br.duplicated(subset=["Year", "Person_id"], keep=False)]
    if len(same_year_dups) > 0:
        raise RuntimeError(
            "ERRO: Person_id duplicado no mesmo ano!\n"
            + same_year_dups[["Year", "Full name", "Person_canonical", "University"]].to_string()
        )

    br = br.sort_values(["Year_int", "Person_canonical"]).reset_index(drop=True)

    # 1. Tabela completa de participações brasileiras
    out_cols = [
        "Year",
        "Pos",
        "Person_id",
        "Person_canonical",
        "Full name",
        "First name",
        "Family name",
        "University_canonical",
        "University_full_name",
        "OBM_team",
        "University",
        "Country",
        "Code",
        "P1",
        "P2",
        "P3",
        "P4",
        "P5",
        "P6",
        "Total",
        "Prize",
        "Prize_raw",
    ]
    p_all = OUT_DIR / "ciim_brazil_participations.csv"
    br[out_cols].to_csv(p_all, index=False, encoding="utf-8")

    # 2. Resumo por pessoa única
    people_rows = []
    for pid, g in br.groupby("Person_id", sort=True):
        g = g.sort_values("Year_int")
        canon = g["Person_canonical"].iloc[0]
        years = g["Year"].tolist()
        univs = list(dict.fromkeys(u for u in g["University_canonical"].tolist() if u != "Não informado"))
        prizes = g["Prize"].tolist()
        totals = pd.to_numeric(g["Total"], errors="coerce").dropna()
        best_tot = f"{totals.max():.0f}" if len(totals) else ""
        pc = g["Prize"].value_counts().to_dict()
        raw_variants = sorted(set(g["Full name"].tolist()))
        prizes_by_year = " | ".join(
            f"{r['Year']}: {r['Prize'] or 'Sem prêmio'}"
            + (f" ({r['Total']} pts)" if r["Total"] else "")
            + (f" [{r['University_canonical']}]" if r["University_canonical"] != "Não informado" else "")
            for _, r in g.iterrows()
        )
        people_rows.append(
            {
                "Person_id": pid,
                "Person_canonical": canon,
                "Participations_total": len(g),
                "Years": ", ".join(years),
                "Universities": " | ".join(univs),
                "OBM_team_participations": int(g["OBM_team"].sum()),
                "Best_Prize": best_prize(prizes),
                "Best_Total": best_tot,
                "Gold_Special": pc.get("Gold Special", 0),
                "Gold": pc.get("Gold", 0),
                "Silver": pc.get("Silver", 0),
                "Bronze": pc.get("Bronze", 0),
                "Honourable_Mention": pc.get("Honourable Mention", 0),
                "No_Prize": pc.get("", 0),
                "Prizes_by_year": prizes_by_year,
                "Name_variants_count": len(raw_variants),
                "Name_variants": " | ".join(raw_variants),
            }
        )
    people_df = pd.DataFrame(people_rows)
    people_df["_bp_ord"] = people_df["Best_Prize"].map(PRIZE_ORDER)
    people_df = people_df.sort_values(
        ["Participations_total", "Gold_Special", "Gold", "Silver", "Bronze", "_bp_ord", "Person_canonical"],
        ascending=[False, False, False, False, False, True, True],
    ).drop(columns=["_bp_ord"])
    p_people = OUT_DIR / "ciim_brazil_people.csv"
    people_df.to_csv(p_people, index=False, encoding="utf-8")

    # 3. Resumo por instituição brasileira
    univ_rows = []
    for ucanon, g in br.groupby("University_canonical", sort=True):
        g = g.sort_values("Year_int")
        pc = g["Prize"].value_counts().to_dict()
        raw_variants = sorted(set(v for v in g["University"].tolist() if v))
        univ_rows.append(
            {
                "University_canonical": ucanon,
                "University_full_name": g["University_full_name"].iloc[0],
                "Participations": len(g),
                "Unique_students": g["Person_id"].nunique(),
                "Years_active": g["Year"].nunique(),
                "First_year": int(g["Year_int"].min()),
                "Last_year": int(g["Year_int"].max()),
                "Gold_Special": pc.get("Gold Special", 0),
                "Gold": pc.get("Gold", 0),
                "Silver": pc.get("Silver", 0),
                "Bronze": pc.get("Bronze", 0),
                "Honourable_Mention": pc.get("Honourable Mention", 0),
                "No_Prize": pc.get("", 0),
                "Raw_variants_count": len(raw_variants),
                "Raw_variants": " | ".join(raw_variants),
            }
        )
    univ_df = pd.DataFrame(univ_rows).sort_values(
        ["Participations", "Gold_Special", "Gold", "Silver"],
        ascending=[False, False, False, False],
    )
    p_univs = OUT_DIR / "ciim_brazil_universities.csv"
    univ_df.to_csv(p_univs, index=False, encoding="utf-8")

    # 4. Resumo por ano
    year_rows = []
    for yr in range(2009, 2027):
        g = br[br["Year_int"] == yr]
        pc = g["Prize"].value_counts().to_dict()
        year_rows.append(
            {
                "Year": yr,
                "Participations": len(g),
                "Institutions": g[g["University_canonical"] != "Não informado"]["University_canonical"].nunique(),
                "OBM_team": int(g["OBM_team"].sum()),
                "Gold_Special": pc.get("Gold Special", 0),
                "Gold": pc.get("Gold", 0),
                "Silver": pc.get("Silver", 0),
                "Bronze": pc.get("Bronze", 0),
                "Honourable_Mention": pc.get("Honourable Mention", 0),
                "No_Prize": pc.get("", 0),
            }
        )
    year_df = pd.DataFrame(year_rows)
    p_year = OUT_DIR / "ciim_brazil_by_year.csv"
    year_df.to_csv(p_year, index=False, encoding="utf-8")

    # Relatório resumido
    multi_variant_people = people_df[people_df["Name_variants_count"] > 1]
    print("=== FILTRO BRASIL CIIM (2009-2026) CONCLUÍDO ===")
    print(f"Total de participações brasileiras: {len(br)}")
    print(f"Estudantes únicos identificados:    {len(people_df)}")
    print(f"Pessoas com grafias unificadas:     {len(multi_variant_people)}")
    print(f"Instituições/delegações canônicas:  {len(univ_df)} (a partir de {br['University'].nunique()} grafias distintas)")
    print(f"Conflitos de Person_id no mesmo ano: 0")
    print("\n--- Instituições brasileiras ---")
    print(
        univ_df[
            [
                "University_canonical",
                "Participations",
                "Unique_students",
                "Gold_Special",
                "Gold",
                "Silver",
                "Bronze",
                "Honourable_Mention",
                "Raw_variants_count",
            ]
        ].to_string(index=False)
    )
    print("\n--- Top 15 estudantes com mais participações na CIIM ---")
    print(
        people_df[
            [
                "Person_canonical",
                "Participations_total",
                "Years",
                "Universities",
                "Gold_Special",
                "Gold",
                "Silver",
                "Bronze",
                "Name_variants_count",
            ]
        ]
        .head(15)
        .to_string(index=False)
    )
    print(f"\n--- Todas as {len(multi_variant_people)} pessoas com múltiplas grafias unificadas ---")
    for _, r in multi_variant_people.sort_values("Person_canonical").iterrows():
        print(f"  {r['Person_canonical']} ({r['Participations_total']}x): {r['Name_variants']}")
    print("\nArquivos gerados:")
    for p in [p_all, p_people, p_univs, p_year]:
        print(f"  - {p.relative_to(ROOT_DIR)}")


if __name__ == "__main__":
    main()
