"""Normaliza cidades, estados e nomes de premiados da OBM (1979-2025), com foco dedicado no Nível Universitário (2001-2025).

Saídas:
- data/obm/processed/university/obm_university_participations.csv (todas as premiações do Nível Universitário normalizadas)
- data/obm/processed/university/obm_university_people.csv         (1 linha por estudante único no Nível Universitário)
- data/obm/processed/university/obm_university_by_state.csv       (resumo por UF no Nível Universitário)
- data/obm/processed/university/obm_university_by_year.csv        (série histórica anual 2001-2025)
- data/obm/processed/summary/obm_all_by_year_level.csv            (série anual por nível, 1979-2025)
- data/obm/processed/summary/obm_all_by_state.csv                 (resumo histórico por UF, todos os níveis)
- data/obm/processed/summary/obm_all_by_city.csv                  (resumo histórico por cidade canônica + UF)
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
INPUT_CSV = ROOT_DIR / "data" / "obm" / "processed" / "obm_results_all_years.csv"
UNIV_OUT_DIR = ROOT_DIR / "data" / "obm" / "processed" / "university"
SUMMARY_OUT_DIR = ROOT_DIR / "data" / "obm" / "processed" / "summary"

# Mapa auditado de abreviações e typos de cidades por (UF, chave ASCII normalizada) -> Cidade canônica
CITY_ALIAS_MAP: dict[tuple[str, str], str] = {
    ("AL", "u dos palmares"): "União dos Palmares",
    ("CE", "s g do amarante"): "São Gonçalo do Amarante",
    ("ES", "venda do imigrante"): "Venda Nova do Imigrante",
    ("GO", "ap de goiania"): "Aparecida de Goiânia",
    ("GO", "s l de montes belos"): "São Luís de Montes Belos",
    ("MG", "b horizonte"): "Belo Horizonte",
    ("MG", "belo h"): "Belo Horizonte",
    ("MG", "c lafayete"): "Conselheiro Lafaiete",
    ("MG", "igarapi"): "Igarapé",
    ("PB", "campina g"): "Campina Grande",
    ("PE", "c de sto agostinho"): "Cabo de Santo Agostinho",
    ("PE", "j dos g"): "Jaboatão dos Guararapes",
    ("PE", "j dos guararapes"): "Jaboatão dos Guararapes",
    ("PE", "jaboatao dos g"): "Jaboatão dos Guararapes",
    ("PE", "joboatao dos guararapes"): "Jaboatão dos Guararapes",
    ("PI", "s r nonato"): "São Raimundo Nonato",
    ("PR", "cuiritiba"): "Curitiba",
    ("RJ", "b j do itabapoana"): "Bom Jesus do Itabapoana",
    ("RJ", "parati"): "Paraty",
    ("RJ", "r de janeiro"): "Rio de Janeiro",
    ("RJ", "rezende"): "Resende",
    ("RJ", "rio de janeio"): "Rio de Janeiro",
    ("RJ", "rio janeiro"): "Rio de Janeiro",
    ("RS", "f westphalen"): "Frederico Westphalen",
    ("SC", "florianooplis"): "Florianópolis",
    ("SC", "florianoopolis"): "Florianópolis",
    ("SP", "franca"): "Franca",
    ("SP", "itibaia"): "Atibaia",
    ("SP", "loureira"): "Louveira",
    ("SP", "m das cruzes"): "Mogi das Cruzes",
    ("SP", "p prudente"): "Presidente Prudente",
    ("SP", "s b do campo"): "São Bernardo do Campo",
    ("SP", "s c do rio pardo"): "Santa Cruz do Rio Pardo",
    ("SP", "s caetano do sul"): "São Caetano do Sul",
    ("SP", "s j da boa vista"): "São João da Boa Vista",
    ("SP", "s j do rio pardo"): "São José do Rio Pardo",
    ("SP", "s j do rio preto"): "São José do Rio Preto",
    ("SP", "s j rio preto"): "São José do Rio Preto",
    ("SP", "sj de rio preto"): "São José do Rio Preto",
    ("SP", "s j dos c"): "São José dos Campos",
    ("SP", "s j dos campos"): "São José dos Campos",
    ("SP", "s j campos"): "São José dos Campos",
    ("SP", "sj dos campos"): "São José dos Campos",
    ("SP", "s r do passa quatro"): "Santa Rita do Passa Quatro",
    ("SP", "sta rita do passa quatro"): "Santa Rita do Passa Quatro",
    ("SP", "sta b d oeste"): "Santa Bárbara d'Oeste",
    ("SP", "santa barbara d oeste"): "Santa Bárbara d'Oeste",
    ("SP", "sao paula"): "São Paulo",
    ("SP", "sao paullo"): "São Paulo",
}

# Equivalências auditadas de nomes de estudantes no Nível Universitário (2001-2025)
# (Irmãos como Daniel vs Davi Lopes Alves de Medeiros e Márcio vs Moyses Assad Cohen NÃO são mesclados!)
UNIV_PERSON_ALIAS_MAP: dict[str, str] = {
    "adenilson arcanjo de moura junior": "Adenilson Arcanjo de Moura Júnior",
    "adrian alexander delgado": "Adrian Alexander Ticona Delgado",
    "adrian alexander ticona delgado": "Adrian Alexander Ticona Delgado",
    "ailton jose da silva junior": "Ailton José da Silva Júnior",
    "alexandre azevedo cesar": "Alexandre Azevedo César",
    "alysson espindola de sa silveira": "Alysson Espíndola de Sá Silveira",
    "andre macieira braga": "André Macieira Braga Costa",
    "andre macieira braga costa": "André Macieira Braga Costa",
    "antonio carlos maldonado s a munhoz": "Antonio Carlos Maldonado S. Alonso Munhoz",
    "antonio carlos maldonado s alonso munhoz": "Antonio Carlos Maldonado S. Alonso Munhoz",
    "antonio deromir neves silva junior": "Antônio Deromir Neves da Silva Júnior",
    "antonio deromir neves da silva junior": "Antônio Deromir Neves da Silva Júnior",
    "arnaldo joao do nascimento jr": "Arnaldo João do Nascimento Junior",
    "arnaldo joao do nascimento junior": "Arnaldo João do Nascimento Junior",
    "caio cesar saldanha maia o kinelski": "Caio Cesar Saldanha Maria Orejuela Kinelski",
    "caio cesar saldanha maria orejuela kinelski": "Caio Cesar Saldanha Maria Orejuela Kinelski",
    "caio ishizara costa": "Caio Ishizaka Costa",
    "caio ishizaka costa": "Caio Ishizaka Costa",
    "cassio henrique vieira morais": "Cássio Henrique Vieira Morais",
    "davi maximo alexandrino nogueira": "Davi Máximo Alexandrino Nogueira",
    "diogo diniz p s silva": "Diogo Diniz Pereira da Silva e Silva",
    "diogo diniz pereira da silva e silva": "Diogo Diniz Pereira da Silva e Silva",
    "domingos dellamonica junior": "Domingos Dellamonica Júnior",
    "eduardo poco": "Eduardo de Moraes Rodrigues Poço",
    "eduardo de moraes rodrigues poco": "Eduardo de Moraes Rodrigues Poço",
    "erik fernando de amorim": "Érik Fernando de Amorim",
    "erik gabriel araujo de medeiros": "Erik Gabriel Araújo de Medeiros",
    "estillac lins maciel borges filho": "Estillac Lins Maciel Borges Filho",
    "evandro makiyama": "Evandro Makiyama de Melo",
    "evandro makiyama de melo": "Evandro Makiyama de Melo",
    "gabriel luis mello dalalio": "Gabriel Luís Mello Dalalio",
    "gabriel tostes mesias pereira": "Gabriel Tostes Messias Pereira",
    "gabriel tostes messias pereira": "Gabriel Tostes Messias Pereira",
    "gabriel vinicius de souza silva": "Gabriel Vinícius de Souza Silva",
    "gustavo gomes araujo": "Gustavo Gomes de Araujo",
    "gustavo gomes de araujo": "Gustavo Gomes de Araujo",
    "helder toshiro susuki": "Helder Toshiro Suzuki",
    "helder toshiro suzuki": "Helder Toshiro Suzuki",
    "henrique gasparini fiuza do nascimento": "Henrique Gasparini Fiúza do Nascimento",
    "iuri antonio nunes de almeida": "Iuri Antônio Nunes de Almeida",
    "joao pedro de abreu marciano": "João Pedro de Abreu Marciano",
    "joao pero de abreu marciano": "João Pedro de Abreu Marciano",
    "joao pedro sedeu godoi": "João Pedro Sedeu Godoi",
    "kellem correa santos": "Kellem Corrêa Santos",
    "leonardo carvalho de luca": "Leonardo Carvalho de Luca",
    "leonardo ferreira": "Leonardo Ferreira Bielinski",
    "leonardo ferreira bielinski": "Leonardo Ferreira Bielinski",
    "levi maximo viana": "Levi Máximo Viana",
    "luca mattos moller": "Luca Mattos Möller",
    "luis daniel barbosa coelho": "Luís Daniel Barbosa Coelho",
    "luize mello d urso vianna": "Luíze Mello D'Urso Vianna",
    "marcelo t de sa oliveira sales": "Marcelo Tadeu de Sá Oliveira Sales",
    "marcelo tadeu de sa oliveira sales": "Marcelo Tadeu de Sá Oliveira Sales",
    "marcio afonso assad cohen": "Márcio Afonso Assad Cohen",
    "marcos tulio barbosa": "Marcos Túlio Barbosa Abreu",
    "marcos tulio barbosa abreu": "Marcos Túlio Barbosa Abreu",
    "pedro henrique milet pinheiro pereira": "Pedro Henrique Milet Pinheiro Pereira",
    "pedro meira de vasconcelos bezerra": "Pedro Meira de Vasconcellos Bezerra",
    "pedro meira de vasconcellos bezerra": "Pedro Meira de Vasconcellos Bezerra",
    "rafael alves da ponte": "Rafael Alves da Ponte",
    "rafael pereira de paula lucas simon": "Rafael Pereira de Paula de Lucas Simon",
    "rafael pereira de paula de lucas simon": "Rafael Pereira de Paula de Lucas Simon",
    "ramon moreira nunes": "Ramon Moreira Nunes",
    "ricardo turolla bortoloti": "Ricardo Turolla Bortolotti",
    "ricardo turolla bortolotti": "Ricardo Turolla Bortolotti",
    "roberio soares nunes": "Robério Soares Nunes",
    "thiago silva pinheiro": "Thiago da Silva Pinheiro",
    "thiago da silva pinheiro": "Thiago da Silva Pinheiro",
    "victor tadeu tetsuo susuki": "Victor Tadeu Tetsuo Suzuki",
    "victor tadeu tetsuo suzuki": "Victor Tadeu Tetsuo Suzuki",
}

PRIZE_ORDER = {
    "Ouro Especial": 1,
    "Ouro": 2,
    "Prata": 3,
    "Bronze": 4,
    "Menção Honrosa": 5,
    "Destaque Regional": 6,
}


def strip_accents(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")


def norm_key(s: str) -> str:
    s = strip_accents(str(s)).lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def slug_id(name: str) -> str:
    return re.sub(r"\s+", "_", norm_key(name))


def choose_best_spelling(variants: list[str]) -> str:
    def score(s: str) -> tuple[int, int, int, int]:
        not_all_caps = 1 if (s != s.upper() and s != s.lower()) else 0
        no_mid_caps = 0 if re.search(r"[a-z][A-Z]", s) else 1
        accents = sum(1 for ch in s if ord(ch) > 127)
        return (not_all_caps, no_mid_caps, accents, len(s))
    return max(variants, key=score)


def main() -> None:
    UNIV_OUT_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_OUT_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(INPUT_CSV, dtype=str).fillna("")
    df["Year_int"] = df["Year"].astype(int)

    # 1. Normalização de cidades em toda a OBM (agrupando por State + chave ASCII)
    city_groups: dict[tuple[str, str], list[str]] = {}
    for _, r in df.iterrows():
        st, ct = r["State"], r["City"]
        if ct:
            city_groups.setdefault((st, norm_key(ct)), []).append(ct)
    best_city = {k: choose_best_spelling(vs) for k, vs in city_groups.items()}

    def canon_city(st: str, ct: str) -> str:
        if not ct:
            return ""
        k = (st, norm_key(ct))
        if k in CITY_ALIAS_MAP:
            return CITY_ALIAS_MAP[k]
        return best_city.get(k, ct)

    df["City_canonical"] = [canon_city(st, ct) for st, ct in zip(df["State"], df["City"])]

    # -----------------------------------------------------------------------
    # A. Nível Universitário (2001-2025) com normalização completa de pessoas
    # -----------------------------------------------------------------------
    u = df[df["Level"] == "Nível Universitário"].copy()
    ascii_groups: dict[str, list[str]] = {}
    for raw_name in u["Full name"]:
        cleaned = re.sub(r"\s+", " ", raw_name).strip()
        ascii_groups.setdefault(norm_key(cleaned), []).append(cleaned)
    fallback_best = {k: choose_best_spelling(vs) for k, vs in ascii_groups.items()}

    def canon_person(raw_name: str) -> str:
        cleaned = re.sub(r"\s+", " ", raw_name).strip()
        k = norm_key(cleaned)
        if k in UNIV_PERSON_ALIAS_MAP:
            return UNIV_PERSON_ALIAS_MAP[k]
        return fallback_best.get(k, cleaned)

    u["Person_canonical"] = u["Full name"].apply(canon_person)
    u["Person_id"] = u["Person_canonical"].apply(slug_id)

    # Segurança: nenhum Person_id pode aparecer 2x no mesmo ano no Nível Universitário!
    dups = u[u.duplicated(subset=["Year", "Person_id"], keep=False)]
    if len(dups) > 0:
        raise RuntimeError(
            "ERRO: Person_id duplicado no mesmo ano na OBM-U!\n"
            + dups[["Year", "Full name", "Person_canonical", "City", "State"]].to_string()
        )

    u = u.sort_values(["Year_int", "Rank_in_level"]).reset_index(drop=True)
    univ_cols = [
        "Year",
        "Edition",
        "Rank_in_level",
        "Person_id",
        "Person_canonical",
        "Full name",
        "City_canonical",
        "State",
        "City",
        "City_State_raw",
        "Points",
        "Prize",
        "Prize_raw",
    ]
    p_u_part = UNIV_OUT_DIR / "obm_university_participations.csv"
    u[univ_cols].to_csv(p_u_part, index=False, encoding="utf-8")

    # 1 linha por estudante único na OBM-U
    people_rows = []
    for pid, g in u.groupby("Person_id", sort=True):
        g = g.sort_values("Year_int")
        pc = g["Prize"].value_counts().to_dict()
        pts = pd.to_numeric(g["Points"], errors="coerce").dropna()
        best_pts = f"{pts.max():.0f}" if len(pts) else ""
        states = list(dict.fromkeys(s for s in g["State"] if s))
        cities = list(dict.fromkeys(f"{c}-{s}" for c, s in zip(g["City_canonical"], g["State"]) if c))
        raw_variants = sorted(set(g["Full name"].tolist()))
        prizes_by_year = " | ".join(
            f"{r['Year']}: {r['Prize']} ({r['Points']} pts, {r['City_canonical']}-{r['State']})"
            for _, r in g.iterrows()
        )
        people_rows.append(
            {
                "Person_id": pid,
                "Person_canonical": g["Person_canonical"].iloc[0],
                "Awards_total": len(g),
                "Years": ", ".join(g["Year"].tolist()),
                "States": " | ".join(states),
                "Cities": " | ".join(cities),
                "Best_Prize": min(g["Prize"].tolist(), key=lambda p: PRIZE_ORDER.get(p, 99)),
                "Best_Points": best_pts,
                "Ouro_Especial": pc.get("Ouro Especial", 0),
                "Ouro": pc.get("Ouro", 0),
                "Prata": pc.get("Prata", 0),
                "Bronze": pc.get("Bronze", 0),
                "Mencao_Honrosa": pc.get("Menção Honrosa", 0),
                "Prizes_by_year": prizes_by_year,
                "Name_variants_count": len(raw_variants),
                "Name_variants": " | ".join(raw_variants),
            }
        )
    people_df = pd.DataFrame(people_rows)
    people_df["_bp"] = people_df["Best_Prize"].map(PRIZE_ORDER)
    people_df = people_df.sort_values(
        ["Awards_total", "Ouro_Especial", "Ouro", "Prata", "Bronze", "_bp", "Person_canonical"],
        ascending=[False, False, False, False, False, True, True],
    ).drop(columns=["_bp"])
    p_u_people = UNIV_OUT_DIR / "obm_university_people.csv"
    people_df.to_csv(p_u_people, index=False, encoding="utf-8")

    # Resumo por UF (Nível Universitário)
    u_state_rows = []
    for st, g in u.groupby("State", sort=True):
        pc = g["Prize"].value_counts().to_dict()
        u_state_rows.append(
            {
                "State": st,
                "Awards": len(g),
                "Unique_students": g["Person_id"].nunique(),
                "Ouro_Especial": pc.get("Ouro Especial", 0),
                "Ouro": pc.get("Ouro", 0),
                "Prata": pc.get("Prata", 0),
                "Bronze": pc.get("Bronze", 0),
                "Mencao_Honrosa": pc.get("Menção Honrosa", 0),
            }
        )
    u_state_df = pd.DataFrame(u_state_rows).sort_values(
        ["Awards", "Ouro_Especial", "Ouro", "Prata"], ascending=[False, False, False, False]
    )
    p_u_state = UNIV_OUT_DIR / "obm_university_by_state.csv"
    u_state_df.to_csv(p_u_state, index=False, encoding="utf-8")

    # Resumo anual (Nível Universitário 2001-2025)
    u_year_rows = []
    for yr in range(2001, 2026):
        g = u[u["Year_int"] == yr]
        pc = g["Prize"].value_counts().to_dict()
        u_year_rows.append(
            {
                "Year": yr,
                "Edition": yr - 1978,
                "Awards": len(g),
                "States": g["State"].nunique(),
                "Ouro_Especial": pc.get("Ouro Especial", 0),
                "Ouro": pc.get("Ouro", 0),
                "Prata": pc.get("Prata", 0),
                "Bronze": pc.get("Bronze", 0),
                "Mencao_Honrosa": pc.get("Menção Honrosa", 0),
            }
        )
    u_year_df = pd.DataFrame(u_year_rows)
    p_u_year = UNIV_OUT_DIR / "obm_university_by_year.csv"
    u_year_df.to_csv(p_u_year, index=False, encoding="utf-8")

    # -----------------------------------------------------------------------
    # B. Resumos gerais da OBM (todos os níveis, 1979-2025)
    # -----------------------------------------------------------------------
    yl_rows = []
    for (yr, lvl), g in df.groupby(["Year_int", "Level"], sort=True):
        pc = g["Prize"].value_counts().to_dict()
        yl_rows.append(
            {
                "Year": yr,
                "Edition": yr - 1978,
                "Level": lvl,
                "Total_awards": len(g),
                "Ouro_Especial": pc.get("Ouro Especial", 0),
                "Ouro": pc.get("Ouro", 0),
                "Prata": pc.get("Prata", 0),
                "Bronze": pc.get("Bronze", 0),
                "Mencao_Honrosa": pc.get("Menção Honrosa", 0),
                "Outros_premios": len(g)
                - sum(pc.get(k, 0) for k in ("Ouro Especial", "Ouro", "Prata", "Bronze", "Menção Honrosa")),
            }
        )
    p_all_yl = SUMMARY_OUT_DIR / "obm_all_by_year_level.csv"
    pd.DataFrame(yl_rows).to_csv(p_all_yl, index=False, encoding="utf-8")

    st_rows = []
    for st, g in df[df["State"] != ""].groupby("State", sort=True):
        pc = g["Prize"].value_counts().to_dict()
        st_rows.append(
            {
                "State": st,
                "Total_awards": len(g),
                "Nivel_Universitario": int((g["Level"] == "Nível Universitário").sum()),
                "Ouro_Especial": pc.get("Ouro Especial", 0),
                "Ouro": pc.get("Ouro", 0),
                "Prata": pc.get("Prata", 0),
                "Bronze": pc.get("Bronze", 0),
                "Mencao_Honrosa": pc.get("Menção Honrosa", 0),
            }
        )
    p_all_st = SUMMARY_OUT_DIR / "obm_all_by_state.csv"
    pd.DataFrame(st_rows).sort_values("Total_awards", ascending=False).to_csv(p_all_st, index=False, encoding="utf-8")

    ct_rows = []
    for (st, ct), g in df[df["City_canonical"] != ""].groupby(["State", "City_canonical"], sort=True):
        pc = g["Prize"].value_counts().to_dict()
        raw_c = sorted(set(g["City"].tolist()))
        ct_rows.append(
            {
                "City_canonical": ct,
                "State": st,
                "Total_awards": len(g),
                "Nivel_Universitario": int((g["Level"] == "Nível Universitário").sum()),
                "Ouro": pc.get("Ouro Especial", 0) + pc.get("Ouro", 0),
                "Prata": pc.get("Prata", 0),
                "Bronze": pc.get("Bronze", 0),
                "Mencao_Honrosa": pc.get("Menção Honrosa", 0),
                "Raw_city_variants_count": len(raw_c),
                "Raw_city_variants": " | ".join(raw_c),
            }
        )
    p_all_ct = SUMMARY_OUT_DIR / "obm_all_by_city.csv"
    pd.DataFrame(ct_rows).sort_values("Total_awards", ascending=False).to_csv(p_all_ct, index=False, encoding="utf-8")

    # Relatório resumido
    multi_var = people_df[people_df["Name_variants_count"] > 1]
    print("=== NORMALIZAÇÃO OBM (1979-2025) CONCLUÍDA ===")
    print(f"Total geral (todos os níveis, 1979-2025): {len(df):,} premiações")
    print(f"Cidades brutas -> canônicas:              {df[df['City']!='']['City'].nunique()} -> {df[df['City_canonical']!='']['City_canonical'].nunique()}")
    print(f"Nível Universitário (2001-2025):          {len(u):,} premiações | {len(people_df)} estudantes únicos")
    print(f"Estudantes OBM-U com grafias unificadas:  {len(multi_var)} | Conflitos no mesmo ano: 0")
    print("\n--- Top 12 UFs no Nível Universitário ---")
    print(u_state_df.head(12).to_string(index=False))
    print("\n--- Top 15 estudantes no Nível Universitário ---")
    print(
        people_df[
            ["Person_canonical", "Awards_total", "Years", "States", "Ouro_Especial", "Ouro", "Prata", "Bronze", "Mencao_Honrosa", "Name_variants_count"]
        ]
        .head(15)
        .to_string(index=False)
    )
    print("\nArquivos gerados:")
    for p in [p_u_part, p_u_people, p_u_state, p_u_year, p_all_yl, p_all_st, p_all_ct]:
        print(f"  - {p.relative_to(ROOT_DIR)}")


if __name__ == "__main__":
    main()
