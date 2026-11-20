"""Filtra e normaliza todos os participantes e universidades brasileiras na IMC (1994-2026).

Lida com:
1. Variações de grafia, sigla, idioma, typos e encoding nas universidades (74 grafias -> 27 instituições canônicas).
2. Variações de nome nas pessoas (acentos, maiúsculas, abreviação de nomes do meio, typos,
   encoding antigo e participações de brasileiros por universidades estrangeiras).

Saídas em imc_results/brazil/:
- imc_brazil_participations.csv       (todas as participações: universidades BR + brasileiros no exterior)
- imc_brazil_only_br_universities.csv (somente participações representando instituições do Brasil)
- imc_brazil_people.csv               (resumo consolidado: 1 linha por pessoa única)
- imc_brazil_universities.csv         (resumo consolidado: 1 linha por instituição brasileira)
- imc_brazil_by_year.csv              (resumo anual de participações e premiações)
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd

INPUT_CSV = Path("imc_results/imc_results_all_years.csv")
OUT_DIR = Path("imc_results/brazil")

# Falsos positivos conhecidos com palavras em português/homônimos fora do Brasil
NON_BRAZIL_UNIVERSITIES = {
    "Angola team – Universidade Agostinho Neto",
    "Angola team – Universidade Metodista de Angola",
    'Universidade "Agostonho Neto"',
    "Universidade Agostinho Neto, Angola",
    "Suffolk University",
    "Universidade de Santiago de Compostela",
    "University of KwaZulu-Natal",
}

# Mapeamento (regex sobre nome ASCII normalizado) -> (sigla/nome canônico, nome por extenso)
# Ordem importa: padrões mais específicos primeiro!
BR_UNIVERSITY_RULES: list[tuple[str, str, str]] = [
    (r"\bita\b|tecnol.?g.*aeronaut|techolog.*aeronaut", "ITA", "Instituto Tecnológico de Aeronáutica (ITA)"),
    (r"\bime\b(?!.*usp)|inst?ituto militar de engenharia", "IME", "Instituto Militar de Engenharia (IME)"),
    (r"\bicmc.?usp\b|\bime.?usp\b|\busp\b|universidade de sao paulo|university of sao paulo", "USP", "Universidade de São Paulo (USP)"),
    (r"\bunicamp\b|universidade estadual de campinas|campinas state university", "UNICAMP", "Universidade Estadual de Campinas (UNICAMP)"),
    (r"puc.?rio|pontificia universidade catolica", "PUC-Rio", "Pontifícia Universidade Católica do Rio de Janeiro (PUC-Rio)"),
    (r"\bfgv\b|getulio vargas", "FGV", "Fundação Getulio Vargas (FGV)"),
    (r"\bufrj\b|federal do rio de janeiro", "UFRJ", "Universidade Federal do Rio de Janeiro (UFRJ)"),
    (r"\bufmg\b|federal de minas gerais", "UFMG", "Universidade Federal de Minas Gerais (UFMG)"),
    (r"\bufpe\b|federal.*pernambuco", "UFPE", "Universidade Federal de Pernambuco (UFPE)"),
    (r"\bufc\b|\bufce\b|univer[sd]i[td]ade federal do cear", "UFC", "Universidade Federal do Ceará (UFC)"),
    (r"\buece\b|estadual do cear", "UECE", "Universidade Estadual do Ceará (UECE)"),
    (r"\bufal\b|federal de alagoas", "UFAL", "Universidade Federal de Alagoas (UFAL)"),
    (r"\bufrgs\b|federal do rio grande do sul", "UFRGS", "Universidade Federal do Rio Grande do Sul (UFRGS)"),
    (r"\bufrn\b|federal do rio grande do norte", "UFRN", "Universidade Federal do Rio Grande do Norte (UFRN)"),
    (r"\bufsc\b(?!ar)|federal de santa catarina", "UFSC", "Universidade Federal de Santa Catarina (UFSC)"),
    (r"\bufscar\b|federal de sao carlos", "UFSCar", "Universidade Federal de São Carlos (UFSCar)"),
    (r"\bufba\b|federal da bahia", "UFBA", "Universidade Federal da Bahia (UFBA)"),
    (r"\bufcg\b|federal de campina grande", "UFCG", "Universidade Federal de Campina Grande (UFCG)"),
    (r"\bufu\b|federal de uberlandia", "UFU", "Universidade Federal de Uberlândia (UFU)"),
    (r"\bufpi\b|federal do piaui", "UFPI", "Universidade Federal do Piauí (UFPI)"),
    (r"\bufabc\b|federal do abc", "UFABC", "Universidade Federal do ABC (UFABC)"),
    (r"\bunesp\b|estadual paulista", "UNESP", "Universidade Estadual Paulista (UNESP)"),
    (r"\buel\b|estadual de londrina", "UEL", "Universidade Estadual de Londrina (UEL)"),
    (r"\bfb uni\b", "FB Uni", "Centro Universitário Farias Brito (FB Uni)"),
    (r"olimpiada brasileira de matematica", "OBM", "Olimpíada Brasileira de Matemática (OBM)"),
]

# Normalização de universidades estrangeiras onde brasileiros auditados também competiram
ABROAD_UNIVERSITY_RULES: list[tuple[str, str, str]] = [
    (r"polytechnique", "École Polytechnique", "École Polytechnique (França)"),
    (r"haverford college", "Haverford College", "Haverford College (EUA)"),
    (r"budapest semesters in mathematics", "Budapest Semesters in Mathematics", "Budapest Semesters in Mathematics (Hungria)"),
]

# Correção de caracteres MacRoman corrompidos presentes no PDF de 2005
MACROMAN_NAME_FIXES = {
    "F·bio Dias Moreira": "Fábio Dias Moreira",
    "DiÍgo UchÙa": "Diêgo Uchôa",
    "Leonardo Z„o": "Leonardo Zão",
    "Kellem CorrÍa Santos": "Kellem Corrêa Santos",
}

# Equivalências auditadas de nomes de pessoas (chave ASCII normalizada -> nome canônico)
# Cada entrada foi verificada individualmente por ano + instituição + histórico na IMC.
PERSON_ALIAS_MAP: dict[str, str] = {
    # Acentos / maiúsculas / MacRoman / typos
    "ailton jose da silva junior": "Ailton José da Silva Júnior",
    "ailton silva junior": "Ailton José da Silva Júnior",
    "alex abreu": "Alex Corrêa Abreu",
    "alex correa abreu": "Alex Corrêa Abreu",
    "andre costa": "André Costa",
    "andre rodrigues": "André Linhares Rodrigues",
    "andre linhares rodrigues": "André Linhares Rodrigues",
    "armando barbosa": "José Armando Barbosa Filho",
    "jose armando barbosa filho": "José Armando Barbosa Filho",
    "bernardo freitas paulo da costa": "Bernardo Freitas Paulo da Costa",
    "brendon borck": "Brendon Diniz Borck",
    "brendon diniz borck": "Brendon Diniz Borck",
    "breno marot": "Breno Azevedo Marot",
    "breno azevedo marot": "Breno Azevedo Marot",
    "bruno freire": "Bruno Costa Alves Freire",
    "bruno costa alves freire": "Bruno Costa Alves Freire",
    "bruno luz": "Bruno Visnadi da Luz",
    "bruno visnadi da luz": "Bruno Visnadi da Luz",
    "caio costa": "Caio Augusto de Carvalho Costa",
    "caio augusto de carvalho costa": "Caio Augusto de Carvalho Costa",
    "carlos sampaio": "Carlos Eduardo Pereira Sampaio",
    "carlos eduardo pereira sampaio": "Carlos Eduardo Pereira Sampaio",
    "danilo fernandes": "Danilo Marinho Fernandes",
    "danilo marinho fernandes": "Danilo Marinho Fernandes",
    "davi amorim": "Davi Coelho Amorim",
    "davi coelho amorim": "Davi Coelho Amorim",
    "davi lopes": "Davi Lopes Mederos",
    "davi lopes mederos": "Davi Lopes Mederos",
    "diego uchoa": "Diêgo Uchôa",
    "eduardo famini silva": "Eduardo Famini Silva",
    "eduardo faminin silva": "Eduardo Famini Silva",
    "eduardo silva": "Eduardo Famini Silva",
    "eduardo sodre": "Eduardo Ventilari Sodré",
    "eduardo ventilari sodre": "Eduardo Ventilari Sodré",
    "evadro makiyma de melo": "Evandro Makiyama de Melo",
    "fabio moreira": "Fábio Dias Moreira",
    "fabio dias moreira": "Fábio Dias Moreira",
    "felipe lins dos santos": "Felipe Lins dos Santos",
    "fernando fonseca": "Fernando Fonseca Andrade Oliveira",
    "fernando fonseca andrade oliveira": "Fernando Fonseca Andrade Oliveira",
    "gabriel dalalio": "Gabriel Luis Mello Dalalio",
    "gabriel luis mello dalallio": "Gabriel Luis Mello Dalalio",
    "gabriel shpielman": "Gabriel Dantas Shpielman",
    "gabriel dantas shpielman": "Gabriel Dantas Shpielman",
    "gabriel henriques": "Gabriel Laurentino Silva Henriques",
    "gabriel laurentino": "Gabriel Laurentino Silva Henriques",
    "gabriel laurentino silva henriques": "Gabriel Laurentino Silva Henriques",
    "gabriel de souza silva": "Gabriel Vinícius de Souza Silva",
    "gabriel vinicius de souza silva": "Gabriel Vinícius de Souza Silva",
    "george alencar": "George Lucas Diniz Alencar",
    "george lucas": "George Lucas Diniz Alencar",
    "george lucas diniz alencar": "George Lucas Diniz Alencar",
    "guilherme rodrigues de souza": "Guilherme Rodrigues Nogueira de Souza",
    "guilherme rodrigues nogueira de souza": "Guilherme Rodrigues Nogueira de Souza",
    "jairon batista": "Jairon Henrique Nóia Batista",
    "jairon henrique noia batista": "Jairon Henrique Nóia Batista",
    "joao arthur marques": "João Arthur Marques Linhares",
    "joao arthur marques linhares": "João Arthur Marques Linhares",
    "joao baptista de paula e silva": "João Baptista de Paula e Silva",
    "joao ferreira": "João Vitor Tomaz Alves Ferreira",
    "joao vitor tomaz alves ferreira": "João Vitor Tomaz Alves Ferreira",
    "joao marcelo ribeiro": "João Marcelo Ribeiro Monteiro de Carvalho",
    "joao marcelo ribeiro monteiro de carvalho": "João Marcelo Ribeiro Monteiro de Carvalho",
    "joao pedro oliveira": "João Pedro Oliveira Rodrigues",
    "joao pedro oliveira rodrigues": "João Pedro Oliveira Rodrigues",
    "joao pedro sedeu godoi": "João Pedro Sedeu Godoi",
    "jonatas marinho": "Jônatas Marinho Santos Júnior",
    "jonatas marinho santos junior": "Jônatas Marinho Santos Júnior",
    "kellem correa santos": "Kellem Corrêa Santos",
    "leandro maia": "Leandro Farias Maia",
    "leandro farias maia": "Leandro Farias Maia",
    "leonardo joau": "Leonardo Andrade Joau e Silva",
    "leonardo andrade joau e silva": "Leonardo Andrade Joau e Silva",
    "leonardo zao": "Leonardo Zão",
    "lucas hiroshi hanke harada": "Lucas Hiroshi Hanke Harada",
    "lucas vinicius silveira de lima": "Lucas Vinícius Silveira de Lima",
    "luis felipe giglio": "Luís Felipe Pestana Giglio",
    "luis felipe pestana giglio": "Luís Felipe Pestana Giglio",
    "mateus thimoteo": "Mateus Siqueira Thimóteo",
    "mateus siqueira thimoteo": "Mateus Siqueira Thimóteo",
    "matheus barreto": "Matheus Andrade Barreto",
    "matheus andrade barreto": "Matheus Andrade Barreto",
    "matheus secco": "Matheus Secco Torres da Silva",
    "matheus secco torres da silva": "Matheus Secco Torres da Silva",
    "matheus sulzbacher": "Matheus Militão da Silva Sulzbacher",
    "matheus militao da silva sulzbacher": "Matheus Militão da Silva Sulzbacher",
    "murilo andrade": "Murilo Vasconcelos Andrade",
    "murilo vasconcelos andrade": "Murilo Vasconcelos Andrade",
    "pedro henrique costa": "Pedro Henrique Alencar Costa",
    "pedro henrique alencar costa": "Pedro Henrique Alencar Costa",
    "pedro souza": "Pedro Soares da Costa Mota e Souza",
    "pedro soares da costa mota e souza": "Pedro Soares da Costa Mota e Souza",
    "rafael dos santos": "Rafael Filipe dos Santos",
    "rafael filipe dos santos": "Rafael Filipe dos Santos",
    "rafael rezende": "Rafael Sampaio de Rezende",
    "rafael sampaio de rezende": "Rafael Sampaio de Rezende",
    "regis barbosa": "Régis Prado Barbosa",
    "regis prado barbosa": "Régis Prado Barbosa",
    "renato costa": "Renato Dias Costa",
    "renato dias costa": "Renato Dias Costa",
    "renato medeiros": "Renato Rebouças de Medeiros",
    "renato reboucas de medeiros": "Renato Rebouças de Medeiros",
    "tadeu belfort neto": "Tadeu Pires de Matos Belfort Neto",
    "tadeu pires de matos belfort neto": "Tadeu Pires de Matos Belfort Neto",
    "thiago costa": "Thiago Barros Rodrigues Costa",
    "thiago barros rodrigues costa": "Thiago Barros Rodrigues Costa",
    "thiago leao": "Thiago Landim de Souza Leão",
    "thiago landim de souza leao": "Thiago Landim de Souza Leão",
    "thiago ramos": "Thiago Ribeiro Ramos",
    "thiago ribeiro ramos": "Thiago Ribeiro Ramos",
    "thiago riberio tergolino": "Thiago Ribeiro Tergolino",
    "thiago ribeiro tergolino": "Thiago Ribeiro Tergolino",
    "thomas yoiti sasaki hoshina": "Thomás Yoiti Sasaki Hoshina",
    "thomas yoiti sosaki hoshina": "Thomás Yoiti Sasaki Hoshina",
    "victor brandao": "Victor Brandão André de Medeiros Ribeiro",
    "victor brandao andre de medeiros ribeiro": "Victor Brandão André de Medeiros Ribeiro",
    "victor suzuki": "Victor Tadeu Tetsuo Suzuki",
    "victor tadeu tetsuo suzuki": "Victor Tadeu Tetsuo Suzuki",
    "vitor fontoura": "Vitor Humia Fontoura",
    "vitor humia fontoura": "Vitor Humia Fontoura",
    "yan victor souza guimaraes": "Yan Victor Souza Guimarães",
}

PRIZE_RANK = {
    "Grand Grand First Prize": 1,
    "Grand First Prize": 2,
    "First Prize": 3,
    "Upper Second Prize": 4,
    "Second Prize": 5,
    "Third Prize": 6,
    "Honourable Mention": 7,
    "Special Mention": 8,
    "Certificate": 9,
    "Withdrawn": 10,
    "Disqualified": 11,
    "": 99,
}


def norm_ascii(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", s.lower())).strip()


def classify_br_university(university: str, city: str, country: str) -> tuple[bool, str, str]:
    """Retorna (is_brazilian_university, canonical_short, canonical_full)."""
    if university in NON_BRAZIL_UNIVERSITIES:
        return False, "", ""
    u_norm = norm_ascii(university)
    co_norm = norm_ascii(country)

    for pattern, short_name, full_name in BR_UNIVERSITY_RULES:
        if re.search(pattern, u_norm):
            return True, short_name, full_name

    # Fallback para futuras edições caso Country == Brazil com nova instituição
    if co_norm == "brazil":
        return True, university.strip(), university.strip()
    return False, "", ""


def classify_abroad_university(university: str) -> tuple[str, str]:
    u_norm = norm_ascii(university)
    for pattern, short_name, full_name in ABROAD_UNIVERSITY_RULES:
        if re.search(pattern, u_norm):
            return short_name, full_name
    return university.strip(), university.strip()


def fix_name_encoding(raw_name: str) -> str:
    return MACROMAN_NAME_FIXES.get(raw_name, raw_name)


def pick_best_spelling(variants: list[str]) -> str:
    """Entre variantes equivalentes (mesma chave ASCII), escolhe a com mais acentos e capitalização normal."""
    def score(s: str) -> tuple[int, int, int, str]:
        not_all_caps = 0 if s.isupper() else 1
        accents = sum(1 for ch in s if ord(ch) > 127)
        return (not_all_caps, accents, len(s), s)
    return max(variants, key=score)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(INPUT_CSV, dtype=str).fillna("")

    # 1. Identificar todas as participações representando universidades brasileiras
    br_flags = [
        classify_br_university(u, c, co)
        for u, c, co in zip(df["University"], df["City"], df["Country"])
    ]
    df["Is_Brazilian_University"] = [x[0] for x in br_flags]
    df["University_canonical"] = [x[1] for x in br_flags]
    df["University_full_name"] = [x[2] for x in br_flags]

    # 2. Normalizar nomes de pessoas (fix MacRoman + alias map + agrupamento case/accent-insensitive)
    df["_name_fixed"] = df["Full name"].map(fix_name_encoding)
    df["_name_key"] = df["_name_fixed"].map(norm_ascii)

    def resolve_person(row_key: str, fixed_name: str, key_to_best: dict[str, str]) -> str:
        if row_key in PERSON_ALIAS_MAP:
            return PERSON_ALIAS_MAP[row_key]
        return key_to_best[row_key]

    # Coletar melhor grafia por chave ASCII nos participantes de universidades brasileiras
    br_only = df[df["Is_Brazilian_University"]]
    key_to_variants: dict[str, list[str]] = {}
    for k, v in zip(br_only["_name_key"], br_only["_name_fixed"]):
        key_to_variants.setdefault(k, []).append(v)
    key_to_best = {k: pick_best_spelling(vs) for k, vs in key_to_variants.items()}

    # Conjunto de nomes canônicos de pessoas que participaram por universidade brasileira
    br_canonical_people = {
        PERSON_ALIAS_MAP.get(k, key_to_best[k]) for k in key_to_variants
    }

    # 3. Identificar também participações dessas MESMAS pessoas representando universidades estrangeiras
    inclusion_reasons: list[str] = []
    person_canonicals: list[str] = []
    u_canon_final: list[str] = []
    u_full_final: list[str] = []

    for idx, r in df.iterrows():
        key = r["_name_key"]
        fixed = r["_name_fixed"]
        if r["Is_Brazilian_University"]:
            p_canon = PERSON_ALIAS_MAP.get(key, key_to_best[key])
            inclusion_reasons.append("brazilian_university")
            person_canonicals.append(p_canon)
            u_canon_final.append(r["University_canonical"])
            u_full_final.append(r["University_full_name"])
        else:
            cand = PERSON_ALIAS_MAP.get(key, key_to_best.get(key, ""))
            if cand and cand in br_canonical_people:
                # Verificar compatibilidade temporal (evita homônimo distante no tempo)
                ab_short, ab_full = classify_abroad_university(r["University"])
                inclusion_reasons.append("brazilian_participant_abroad")
                person_canonicals.append(cand)
                u_canon_final.append(ab_short)
                u_full_final.append(ab_full)
            else:
                inclusion_reasons.append("")
                person_canonicals.append("")
                u_canon_final.append("")
                u_full_final.append("")

    df["Inclusion_reason"] = inclusion_reasons
    df["Person_canonical"] = person_canonicals
    df["University_canonical"] = u_canon_final
    df["University_full_name"] = u_full_final

    br_all = df[df["Inclusion_reason"] != ""].copy()
    br_all["Year_int"] = br_all["Year"].astype(int)

    # Atribuir Person_id estável em ordem alfabética de Person_canonical
    sorted_people = sorted(br_all["Person_canonical"].unique(), key=norm_ascii)
    pid_map = {name: f"BR_{i:03d}" for i, name in enumerate(sorted_people, start=1)}
    br_all["Person_id"] = br_all["Person_canonical"].map(pid_map)

    # Ordenar por Year e posição/Sum
    br_all["_pos_num"] = br_all["Pos"].map(lambda s: int(re.findall(r"\d+", s)[0]) if re.findall(r"\d+", s) else 9999)
    br_all = br_all.sort_values(["Year_int", "_pos_num", "Person_canonical"]).reset_index(drop=True)

    # Colunas finais do CSV de participações
    orig_cols = [c for c in pd.read_csv(INPUT_CSV, nrows=0).columns]
    extra_cols = [
        "Person_id",
        "Person_canonical",
        "University_canonical",
        "University_full_name",
        "Is_Brazilian_University",
        "Inclusion_reason",
    ]
    out_cols = extra_cols + orig_cols

    p_all = OUT_DIR / "imc_brazil_participations.csv"
    br_all[out_cols].to_csv(p_all, index=False, encoding="utf-8")

    br_univ_only = br_all[br_all["Is_Brazilian_University"]].copy()
    p_univ_only = OUT_DIR / "imc_brazil_only_br_universities.csv"
    br_univ_only[out_cols].to_csv(p_univ_only, index=False, encoding="utf-8")

    # 4. Resumo por pessoa única (imc_brazil_people.csv)
    people_rows = []
    for pid, grp in br_all.groupby("Person_id", sort=True):
        grp = grp.sort_values("Year_int")
        p_name = grp["Person_canonical"].iloc[0]
        raw_variants = list(dict.fromkeys(grp["Full name"].tolist()))
        years = grp["Year"].tolist()
        br_u = list(dict.fromkeys(grp[grp["Is_Brazilian_University"]]["University_canonical"].tolist()))
        ab_u = list(dict.fromkeys(grp[~grp["Is_Brazilian_University"]]["University_canonical"].tolist()))
        all_u = list(dict.fromkeys(grp["University_canonical"].tolist()))
        prizes = grp["Prize"].tolist()
        best_prize = min(prizes, key=lambda p: PRIZE_RANK.get(p, 99))
        sums = [float(s) for s in grp["Sum"] if re.fullmatch(r"\d+(\.\d+)?", s)]
        best_sum = f"{max(sums):.0f}" if sums else ""
        pc = grp["Prize"].value_counts()
        people_rows.append({
            "Person_id": pid,
            "Person_canonical": p_name,
            "Participations_total": len(grp),
            "Participations_BR_univ": int(grp["Is_Brazilian_University"].sum()),
            "Participations_abroad": int((~grp["Is_Brazilian_University"]).sum()),
            "Years": ", ".join(years),
            "BR_Universities": "; ".join(br_u),
            "Abroad_Universities": "; ".join(ab_u),
            "All_Universities": "; ".join(all_u),
            "Best_Prize": best_prize,
            "Best_Sum": best_sum,
            "Grand_Grand_First": int(pc.get("Grand Grand First Prize", 0)),
            "Grand_First": int(pc.get("Grand First Prize", 0)),
            "First": int(pc.get("First Prize", 0)),
            "Second": int(pc.get("Second Prize", 0)),
            "Third": int(pc.get("Third Prize", 0)),
            "Honourable_Mention": int(pc.get("Honourable Mention", 0)),
            "Certificate": int(pc.get("Certificate", 0)),
            "Prizes_by_year": "; ".join(f"{y}: {p} ({u})" for y, p, u in zip(grp["Year"], grp["Prize"], grp["University_canonical"])),
            "Name_variants_count": len(raw_variants),
            "Name_variants": "; ".join(raw_variants),
        })
    people_df = pd.DataFrame(people_rows)
    people_df["_rk"] = people_df["Best_Prize"].map(lambda p: PRIZE_RANK.get(p, 99))
    people_df = people_df.sort_values(
        ["_rk", "Grand_Grand_First", "Grand_First", "First", "Second", "Third", "Participations_total", "Person_canonical"],
        ascending=[True, False, False, False, False, False, False, True],
    ).drop(columns=["_rk"])
    p_people = OUT_DIR / "imc_brazil_people.csv"
    people_df.to_csv(p_people, index=False, encoding="utf-8")

    # 5. Resumo por universidade brasileira (imc_brazil_universities.csv)
    univ_rows = []
    for u_short, grp in br_univ_only.groupby("University_canonical"):
        u_full = grp["University_full_name"].iloc[0]
        raw_vars = sorted(grp["University"].unique().tolist())
        pc = grp["Prize"].value_counts()
        univ_rows.append({
            "University_canonical": u_short,
            "University_full_name": u_full,
            "Total_Participations": len(grp),
            "Unique_Students": grp["Person_id"].nunique(),
            "First_Year": int(grp["Year_int"].min()),
            "Last_Year": int(grp["Year_int"].max()),
            "Grand_Grand_First": int(pc.get("Grand Grand First Prize", 0)),
            "Grand_First": int(pc.get("Grand First Prize", 0)),
            "First": int(pc.get("First Prize", 0)),
            "Second": int(pc.get("Second Prize", 0)),
            "Third": int(pc.get("Third Prize", 0)),
            "Honourable_Mention": int(pc.get("Honourable Mention", 0)),
            "Certificate": int(pc.get("Certificate", 0)),
            "Raw_variants_count": len(raw_vars),
            "Raw_variants": " | ".join(raw_vars),
        })
    univ_df = pd.DataFrame(univ_rows).sort_values(
        ["Total_Participations", "Unique_Students", "University_canonical"],
        ascending=[False, False, True],
    )
    p_univs = OUT_DIR / "imc_brazil_universities.csv"
    univ_df.to_csv(p_univs, index=False, encoding="utf-8")

    # 6. Resumo anual (imc_brazil_by_year.csv)
    year_rows = []
    for y, grp in br_all.groupby("Year_int"):
        grp_br = grp[grp["Is_Brazilian_University"]]
        pc = grp_br["Prize"].value_counts()
        year_rows.append({
            "Year": int(y),
            "Participants_BR_univ": len(grp_br),
            "Participants_abroad": int((~grp["Is_Brazilian_University"]).sum()),
            "Participants_total": len(grp),
            "BR_Universities_count": grp_br["University_canonical"].nunique(),
            "Grand_Grand_First": int(pc.get("Grand Grand First Prize", 0)),
            "Grand_First": int(pc.get("Grand First Prize", 0)),
            "First": int(pc.get("First Prize", 0)),
            "Second": int(pc.get("Second Prize", 0)),
            "Third": int(pc.get("Third Prize", 0)),
            "Honourable_Mention": int(pc.get("Honourable Mention", 0)),
            "Certificate": int(pc.get("Certificate", 0)),
        })
    year_df = pd.DataFrame(year_rows).sort_values("Year")
    p_year = OUT_DIR / "imc_brazil_by_year.csv"
    year_df.to_csv(p_year, index=False, encoding="utf-8")

    # 7. Auto-checagem: nenhuma pessoa deve aparecer 2 vezes no mesmo ano!
    same_year_dups = br_all[br_all.duplicated(subset=["Year", "Person_id"], keep=False)]
    print(f"Total de participações brasileiras (BR + exterior): {len(br_all)}")
    print(f"  - Representando instituições do Brasil:           {len(br_univ_only)} ({univ_df['University_canonical'].nunique()} instituições, {br_univ_only['University'].nunique()} grafias originais)")
    print(f"  - Mesmos estudantes por instituições no exterior: {len(br_all) - len(br_univ_only)}")
    print(f"Total de estudantes únicos (após normalização):     {len(people_df)} (eram {br_all['Full name'].nunique()} grafias distintas de nome)")
    print(f"Pessoas unificadas com >=2 grafias de nome:         {(people_df['Name_variants_count'] >= 2).sum()}")
    print(f"Conflitos (mesmo Person_id no mesmo ano):           {len(same_year_dups)}")
    if len(same_year_dups):
        print(same_year_dups[["Year", "Person_id", "Person_canonical", "Full name", "University"]])
    print("\nArquivos salvos em imc_results/brazil/:")
    for p in [p_all, p_univ_only, p_people, p_univs, p_year]:
        print(f"  - {p}")


if __name__ == "__main__":
    main()
