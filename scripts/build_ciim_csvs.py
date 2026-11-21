"""Pipeline completo para gerar CSVs padronizados da CIIM (2009-2026).

Fontes em cache local em data/ciim/raw/ (baixadas por scripts/download_ciim.py):
- 2009-2013, 2016, 2017, 2019-2026: PDFs oficiais em data/ciim/raw/pdf/
- 2016, 2018: HTMLs oficiais em data/ciim/raw/html/
- 2014, 2015: transcrições verificadas das imagens oficiais em data/ciim/raw/transcribed/

Saídas:
- data/ciim/processed/by_year/ciim_results_{year}.csv (um CSV por ano, 2009 a 2026)
- data/ciim/processed/ciim_results_all_years.csv      (consolidado com todos os 18 anos)
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import pandas as pd
import pdfplumber
from bs4 import BeautifulSoup

ROOT_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT_DIR / "data" / "ciim" / "raw"
HTML_DIR = RAW_DIR / "html"
PDF_DIR = RAW_DIR / "pdf"
TRANSCRIBED_DIR = RAW_DIR / "transcribed"
OUTPUT_DIR = ROOT_DIR / "data" / "ciim" / "processed"
BY_YEAR_DIR = OUTPUT_DIR / "by_year"

STANDARD_COLUMNS = [
    "Year",
    "Pos",
    "First name",
    "Family name",
    "Full name",
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


def clean_text(val: Any) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    s = str(val).replace("\xa0", " ").replace("\u200b", "").replace("\xad", "")
    s = re.sub(r"\s+", " ", s).strip()
    return unicodedata.normalize("NFC", s)


def clean_num(val: Any) -> str:
    s = clean_text(val)
    if not s or s in {"-", "–", "—", "nan", "None"}:
        return ""
    if re.fullmatch(r"-?\d+\.0+", s):
        return s.split(".")[0]
    return s


def norm_key(s: str) -> str:
    s = unicodedata.normalize("NFKD", clean_text(s)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", s.lower())).strip()


def same_person_in_year(a: str, b: str) -> bool:
    """Detecta se duas entradas no mesmo ano (ex: CuadroHonor vs Concursantes) são a mesma pessoa."""
    ka, kb = norm_key(a), norm_key(b)
    if not ka or not kb:
        return False
    if ka == kb:
        return True
    ta, tb = ka.split(), kb.split()
    if set(ta) == set(tb):
        return True
    # Um é prefixo do outro (ex: 'Guilherme Rodrigues Nogueira de' vs '... de Souza', ou 'Daniel Campos' vs 'Daniel Campos Salas')
    if len(ta) >= 2 and len(tb) >= 2:
        shorter, longer = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
        if longer[: len(shorter)] == shorter:
            return True
        if ta[0] == tb[0] and ta[-1] == tb[-1]:
            return True
    if SequenceMatcher(None, ka, kb).ratio() >= 0.88:
        return True
    return False


def normalize_country(raw: str) -> str:
    s = clean_text(raw)
    if not s:
        return ""
    k = norm_key(s)
    mapping = {
        "br": "Brasil",
        "bra": "Brasil",
        "brasil": "Brasil",
        "brazil": "Brasil",
        "mx": "México",
        "mex": "México",
        "mexico": "México",
        "co": "Colombia",
        "col": "Colombia",
        "colombia": "Colombia",
        "cr": "Costa Rica",
        "crc": "Costa Rica",
        "costa rica": "Costa Rica",
        "ec": "Ecuador",
        "ecu": "Ecuador",
        "ecuador": "Ecuador",
        "equador": "Ecuador",
        "ar": "Argentina",
        "arg": "Argentina",
        "argentina": "Argentina",
        "pe": "Perú",
        "per": "Perú",
        "peru": "Perú",
        "gt": "Guatemala",
        "gua": "Guatemala",
        "guatemala": "Guatemala",
        "ve": "Venezuela",
        "ven": "Venezuela",
        "venezuela": "Venezuela",
        "bo": "Bolivia",
        "bol": "Bolivia",
        "bolivia": "Bolivia",
        "hn": "Honduras",
        "hon": "Honduras",
        "honduras": "Honduras",
        "sv": "El Salvador",
        "esa": "El Salvador",
        "el salvador": "El Salvador",
        "es": "España",
        "esp": "España",
        "espana": "España",
        "espanha": "España",
        "do": "República Dominicana",
        "dom": "República Dominicana",
        "rep dominicana": "República Dominicana",
        "republica dominicana": "República Dominicana",
        "dominica": "Ecuador",  # typo conhecido em 2018 para Andrés David Pincay Peña (ESPOL - Ecuador)
        "ni": "Nicaragua",
        "nic": "Nicaragua",
        "nicaragua": "Nicaragua",
        "pa": "Panamá",
        "pan": "Panamá",
        "panama": "Panamá",
        "cl": "Chile",
        "chi": "Chile",
        "chile": "Chile",
        "cu": "Cuba",
        "cub": "Cuba",
        "cuba": "Cuba",
        "uy": "Uruguay",
        "uru": "Uruguay",
        "uruguay": "Uruguay",
        "py": "Paraguay",
        "par": "Paraguay",
        "paraguay": "Paraguay",
        "pt": "Portugal",
        "por": "Portugal",
        "portugal": "Portugal",
    }
    return mapping.get(k, s)


def normalize_prize(raw: str) -> str:
    s = clean_text(raw)
    if not s:
        return ""
    k = norm_key(s)
    if "no hay" in k or k in {"ninguno", "none", "sin premio", "participacion"}:
        return ""
    if ("oro" in k or "ouro" in k or "gold" in k) and "especial" in k:
        return "Gold Special"
    if "oro" in k or "ouro" in k or "gold" in k or "primer lugar" in k:
        return "Gold"
    if "plata" in k or "prata" in k or "silver" in k or "segundo lugar" in k:
        return "Silver"
    if "bronce" in k or "bronze" in k or "tercer lugar" in k:
        return "Bronze"
    if "menc" in k or "honor" in k or "honr" in k or k.replace(" ", "") == "mh":
        return "Honourable Mention"
    return s


def make_row(year: int, **kwargs: Any) -> dict[str, Any]:
    row = {c: "" for c in STANDARD_COLUMNS}
    row["Year"] = year
    for k, v in kwargs.items():
        if k in row:
            row[k] = v
    fn = clean_text(row["First name"])
    ln = clean_text(row["Family name"])
    full = clean_text(row["Full name"])
    if not full and (fn or ln):
        full = f"{fn} {ln}".strip()
    row["First name"] = fn
    row["Family name"] = ln
    row["Full name"] = full
    row["Pos"] = clean_text(row["Pos"]).rstrip(".")
    row["University"] = clean_text(row["University"])
    row["Country"] = normalize_country(row["Country"])
    row["Code"] = clean_text(row["Code"])
    row["Prize_raw"] = clean_text(row["Prize_raw"] or row["Prize"])
    row["Prize"] = normalize_prize(row["Prize_raw"])
    for c in ["P1", "P2", "P3", "P4", "P5", "P6", "Total"]:
        row[c] = clean_num(row[c])
    return row


# ---------------------------------------------------------------------------
# 2009: ResultadosCIIM2009.pdf (todos os 55 participantes com cortes exatos)
# ---------------------------------------------------------------------------
def parse_2009() -> list[dict[str, Any]]:
    # Cortes confirmados visualmente na pág. 1 de ResultadosCIIM2009.pdf:
    # >= 58: oro especial | 40..53: oro | 25..38: plata | 12..23: bronce | <=11: sem prêmio (NO HAY MENCIONES)
    rows: list[dict[str, Any]] = []
    with pdfplumber.open(PDF_DIR / "ciim_2009_cuadro_de_honor_ResultadosCIIM2009.pdf") as pdf:
        for page in pdf.pages:
            tbl = max(page.extract_tables(), key=len)
            for raw_c in tbl:
                c = [clean_text(x) for x in raw_c]
                if len(c) < 5 or not c[0] or not re.fullmatch(r"\d+", c[4]):
                    continue
                tot = int(c[4])
                if tot >= 58:
                    prize_raw = "Oro Especial"
                elif tot >= 40:
                    prize_raw = "Oro"
                elif tot >= 25:
                    prize_raw = "Plata"
                elif tot >= 12:
                    prize_raw = "Bronce"
                else:
                    prize_raw = ""
                rows.append(
                    make_row(
                        2009,
                        **{
                            "Full name": c[0],
                            "University": c[1],
                            "Country": c[2],
                            "Code": c[3],
                            "Total": c[4],
                            "Prize_raw": prize_raw,
                        },
                    )
                )
    return rows


# ---------------------------------------------------------------------------
# 2010: CuadroHonor-CIIM2010.pdf (premiados) + Concursantes-CIIM2010.pdf (todos)
# ---------------------------------------------------------------------------
def parse_2010() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    with pdfplumber.open(PDF_DIR / "ciim_2010_cuadro_de_honor_CuadroHonor-CIIM2010.pdf") as pdf:
        for page in pdf.pages:
            tbl = max(page.extract_tables(), key=len)
            for raw_c in tbl:
                c = [clean_text(x) for x in raw_c]
                if len(c) < 4 or not c[0] or "erbmoN" in c[0] or c[0].lower() in {"nombre", "nome"}:
                    continue
                seen_keys.add(norm_key(c[0]))
                rows.append(
                    make_row(
                        2010,
                        **{
                            "Full name": c[0],
                            "University": c[1],
                            "Country": c[2],
                            "Prize_raw": c[3],
                        },
                    )
                )

    # Complementa com os estudantes não-premiados de Concursantes-CIIM2010.pdf
    with pdfplumber.open(PDF_DIR / "ciim_2010_concursantes_Concursantes-CIIM2010.pdf") as pdf:
        for page in pdf.pages:
            tbl = max(page.extract_tables(), key=len)
            for raw_c in tbl:
                c = [clean_text(x) for x in raw_c]
                if len(c) < 4:
                    continue
                if "estud" not in norm_key(c[0]):
                    continue
                name = c[1]
                k = norm_key(name)
                if not k:
                    continue
                matched_row = next((r for r in rows if same_person_in_year(r["Full name"], name)), None)
                if matched_row is not None:
                    # Se o nome no CuadroHonor estava truncado (ex: 'Guilherme Rodrigues Nogueira de'), completa!
                    if norm_key(name).startswith(norm_key(matched_row["Full name"]) + " "):
                        matched_row["Full name"] = name
                    continue
                seen_keys.add(k)
                rows.append(
                    make_row(
                        2010,
                        **{
                            "Full name": name,
                            "University": c[2],
                            "Country": c[3],
                            "Prize_raw": "",
                        },
                    )
                )
    return rows


# ---------------------------------------------------------------------------
# 2011: CuadroHonor-CIIM2011.pdf (premiados c/ P1..P6) + Concursantes-CIIM2011.pdf
# ---------------------------------------------------------------------------
def parse_2011() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    current_prize = ""
    with pdfplumber.open(PDF_DIR / "ciim_2011_cuadro_de_honor_CuadroHonor-CIIM2011.pdf") as pdf:
        for page in pdf.pages:
            tbl = max(page.extract_tables(), key=len)
            for raw_c in tbl:
                c = [clean_text(x) for x in raw_c]
                if not any(c):
                    continue
                low0 = norm_key(c[0])
                if any(h in low0 for h in ["medallas de oro", "medallas de plata", "medallas de bronce", "menciones"]):
                    current_prize = c[0]
                    continue
                if not re.fullmatch(r"\d+", c[0]):
                    continue
                note = c[11] if len(c) > 11 and c[11] else ""
                prize_raw = f"{current_prize} ({note})" if note else current_prize
                seen_keys.add(norm_key(c[1]))
                rows.append(
                    make_row(
                        2011,
                        **{
                            "Pos": c[0],
                            "Full name": c[1],
                            "University": c[2],
                            "Country": c[3],
                            "P1": c[4], "P2": c[5], "P3": c[6], "P4": c[7], "P5": c[8], "P6": c[9],
                            "Total": c[10],
                            "Prize_raw": prize_raw,
                        },
                    )
                )

    # Complementa com estudantes não-premiados de Concursantes-CIIM2011.pdf
    cur_univ, cur_country = "", ""
    with pdfplumber.open(PDF_DIR / "ciim_2011_concursantes_Concursantes-CIIM2011.pdf") as pdf:
        for page in pdf.pages:
            tbl = max(page.extract_tables(), key=len)
            for raw_c in tbl:
                c = [clean_text(x) for x in raw_c]
                if len(c) < 5 or norm_key(c[0]) == "equipo":
                    continue
                if c[1]:
                    cur_univ = c[1]
                if c[2]:
                    cur_country = c[2]
                if "estud" not in norm_key(c[3]):
                    continue
                name = c[4]
                k = norm_key(name)
                if not k or any(same_person_in_year(r["Full name"], name) for r in rows):
                    continue
                seen_keys.add(k)
                rows.append(
                    make_row(
                        2011,
                        **{
                            "Full name": name,
                            "University": cur_univ,
                            "Country": cur_country,
                            "Prize_raw": "",
                        },
                    )
                )
    return rows


# ---------------------------------------------------------------------------
# 2012: Resultados-CIIM2012.pdf (todos os participantes) + país por equipe
# ---------------------------------------------------------------------------
TEAM_COUNTRY_2012 = {
    "olimpiada brasileira de matematica": "Brasil",
    "instituto militar de engenharia": "Brasil",
    "instituto militar de engenharia ime": "Brasil",
    "universidade de sao paulo": "Brasil",
    "universidade federal de minas gerais": "Brasil",
    "universidad nacional autonoma de mexico": "México",
    "olimpiada mexicana de matematicas": "México",
    "universidad de guanajuato": "México",
    "universidad de guanajuato cimat": "México",
    "cimat": "México",
    "universidad autonoma de nuevo leon": "México",
    "universidad autonoma del estado de mexico": "México",
    "universidad autonoma de queretaro": "México",
    "benemerita universidad autonoma de puebla": "México",
    "universidad veracruzana": "México",
    "instituto tecnologico y de estudios superiores de monterrey": "México",
    "universidad de sonora": "México",
    "universidad autonoma de yucatan": "México",
    "universidad autonoma de zacatecas": "México",
    "universidad de costa rica": "Costa Rica",
    "cimpa": "Costa Rica",
    "instituto tecnologico de costa rica": "Costa Rica",
    "universidad de los andes": "Colombia",
    "universidad nacional de colombia": "Colombia",
    "universidad industrial de santander": "Colombia",
    "universidad del valle": "Colombia",
    "universidad antonio narino": "Colombia",
    "universidad san francisco de quito": "Ecuador",
    "espol": "Ecuador",
    "escuela superior politecnica del litoral": "Ecuador",
    "escuela politecnica nacional": "Ecuador",
    "universidad de buenos aires": "Argentina",
    "universidad nacional de ingenieria": "Perú",
    "pontificia universidad catolica del peru": "Perú",
    "universidad de san carlos de guatemala": "Guatemala",
    "universidad del valle de guatemala": "Guatemala",
    "universidad simon bolivar": "Venezuela",
    "universidad de los andes de merida": "Venezuela",
}


def infer_country_from_univ(univ: str) -> str:
    k = norm_key(univ)
    if k in TEAM_COUNTRY_2012:
        return TEAM_COUNTRY_2012[k]
    patterns = [
        (r"\bobm\b|\bime\d*\b|\bita\d*\b|\busp\b|\bufmg\b|\bufc\b|\bufal\b|\bufpe\b|\bufsc\b|\bufrj\b|\buea\b|\bunicamp\b|\bpuc\d*.*rio\b|\bpuc\d*\s+rj\b|\bfgv\b|\bemap\b|getulio vargas|brasil|sao paulo|minas gerais|campinas|pernambuco|alagoas|ceara|rio de janeiro|militar de eng|aeronaut", "Brasil"),
        (r"\bomm\b|\bunam\b|\bcimat\b|\buanl\b|\buaem\b|\buaz\b|\buaq\b|\bbuap\b|\bual\b|\bux\b|\bmex\b|distrito federal|mexico|mexican|monterrey|guanajuato|veracruz|yucatan|puebla|queretaro|sonora|zacatecas|chihuahua|guadalajara|sinaloa|chiapas|michoacan|tamaulipas|coahuila", "México"),
        (r"\bcimpa\b|\bucr\b|\bitcr\b|\btec\b|\bolcoma\b|costa rica", "Costa Rica"),
        (r"\busfq\b|\bespol\b|\bepn\b|\bomec\b|es pol nacional|ecuador|ecuatorian|quito|guayaquil|litoral", "Ecuador"),
        (r"\bunal\b|\buan\b|\buis\b|\bunc\d*\b|\buniandes\b|\beafit\b|\bjaveriana\b|\bocm\b|colombia|antioquia|del valle|los andes(?!.*merida)|del norte|industrial de santander|medellin|bogota|manizales|armenia", "Colombia"),
        (r"\buba\b|buenos aires|argentin|cordoba.*arg|rosario", "Argentina"),
        (r"\busac\b|\buscg\b|\buvg\b|\bomg\b|guatemal|galileo|mesoam[ae]ricana", "Guatemala"),
        (r"simon bolivar|venezuel|merida", "Venezuela"),
        (r"san andres|bolivian|bolivia", "Bolivia"),
        (r"peru|ingenieria.*peru", "Perú"),
        (r"rioja|complutense|espana|barcelona|madrid|valencia|zaragoza", "España"),
        (r"honduras|unah", "Honduras"),
        (r"el salvador", "El Salvador"),
        (r"dominicana", "República Dominicana"),
        (r"nicaragua", "Nicaragua"),
        (r"panama", "Panamá"),
    ]
    for pat, country in patterns:
        if re.search(pat, k):
            return country
    return ""


def parse_2012() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    current_team = ""
    with pdfplumber.open(PDF_DIR / "ciim_2012_resultados_Resultados-CIIM2012.pdf") as pdf:
        for page in pdf.pages:
            tbl = max(page.extract_tables(), key=len)
            for raw_c in tbl:
                c = [clean_text(x) for x in raw_c]
                if len(c) < 9 or not c[0]:
                    continue
                low0 = norm_key(c[0])
                if low0 in {"puntajes oficiales", "nombre", "cuadro de honor"}:
                    continue
                # Linha de cabeçalho de equipe: c[0] tem nome da equipe e c[1..7] vazios
                if not any(c[1:8]):
                    current_team = c[0]
                    continue
                if not re.fullmatch(r"\d+", c[7]):
                    continue
                rows.append(
                    make_row(
                        2012,
                        **{
                            "Full name": c[0],
                            "University": current_team,
                            "Country": infer_country_from_univ(current_team),
                            "P1": c[1], "P2": c[2], "P3": c[3], "P4": c[4], "P5": c[5], "P6": c[6],
                            "Total": c[7],
                            "Prize_raw": c[8],
                        },
                    )
                )
    return rows


# ---------------------------------------------------------------------------
# 2013: Resultados + CuadroHonor (medalhas) + Concursantes (país)
# ---------------------------------------------------------------------------
def parse_2013() -> list[dict[str, Any]]:
    # 1. Mapa de país via Concursantes-CIIM2013.pdf
    country_by_name: dict[str, str] = {}
    country_by_univ: dict[str, str] = {}
    with pdfplumber.open(PDF_DIR / "ciim_2013_concursantes_Concursantes-CIIM2013.pdf") as pdf:
        for page in pdf.pages:
            tbl = max(page.extract_tables(), key=len)
            for raw_c in tbl:
                c = [clean_text(x) for x in raw_c]
                if len(c) < 5 or norm_key(c[0]) == "apellidos" or "concursantes" in norm_key(c[0]):
                    continue
                full = f"{c[1]} {c[0]}".strip()
                if c[3]:
                    country_by_name[norm_key(full)] = c[3]
                    if c[4]:
                        country_by_univ[norm_key(c[4])] = c[3]

    # 2. Mapa de medalhas via CuadroHonor-CIIM2013.pdf
    prize_by_name: dict[str, str] = {}
    with pdfplumber.open(PDF_DIR / "ciim_2013_cuadro_de_honor_CuadroHonor-CIIM2013.pdf") as pdf:
        for page in pdf.pages:
            tbl = max(page.extract_tables(), key=len)
            for raw_c in tbl:
                c = [clean_text(x) for x in raw_c]
                if len(c) < 5 or not c[0] or norm_key(c[0]) == "apellidos" or "cuadro" in norm_key(c[0]):
                    continue
                full = f"{c[1]} {c[0]}".strip()
                prize_by_name[norm_key(full)] = c[4]

    # 3. Todos os participantes e notas via Resultados-CIIM2013.pdf
    rows: list[dict[str, Any]] = []
    with pdfplumber.open(PDF_DIR / "ciim_2013_resultados_Resultados-CIIM2013.pdf") as pdf:
        for page in pdf.pages:
            tbl = max(page.extract_tables(), key=len)
            for raw_c in tbl:
                c = [clean_text(x) for x in raw_c]
                if len(c) < 10 or not c[0] or norm_key(c[0]) == "apellidos" or "resultados" in norm_key(c[0]):
                    continue
                if not re.fullmatch(r"\d+", c[9]):
                    continue
                fn, ln, univ = c[1], c[0], c[2]
                full = f"{fn} {ln}".strip()
                nk = norm_key(full)
                country = (
                    country_by_name.get(nk)
                    or country_by_univ.get(norm_key(univ))
                    or infer_country_from_univ(univ)
                )
                prize_raw = prize_by_name.get(nk, "")
                rows.append(
                    make_row(
                        2013,
                        **{
                            "First name": fn,
                            "Family name": ln,
                            "Full name": full,
                            "University": univ,
                            "Country": country,
                            "P1": c[3], "P2": c[4], "P3": c[5], "P4": c[6], "P5": c[7], "P6": c[8],
                            "Total": c[9],
                            "Prize_raw": prize_raw,
                        },
                    )
                )
    return rows


# ---------------------------------------------------------------------------
# 2014 e 2015: CSVs transcritos e verificados das imagens oficiais
# ---------------------------------------------------------------------------
def parse_2014() -> list[dict[str, Any]]:
    df = pd.read_csv(TRANSCRIBED_DIR / "ciim_2014.csv", dtype=str).fillna("")
    rows = []
    for _, r in df.iterrows():
        rows.append(make_row(2014, **r.to_dict()))
    return rows


def parse_2015() -> list[dict[str, Any]]:
    df = pd.read_csv(TRANSCRIBED_DIR / "ciim_2015.csv", dtype=str).fillna("")
    rows = []
    for _, r in df.iterrows():
        d = r.to_dict()
        d["Country"] = infer_country_from_univ(d["University"])
        rows.append(make_row(2015, **d))
    return rows


# ---------------------------------------------------------------------------
# 2016: HTML cuadro de honor + Concursantes-CIIM2016.pdf (não-premiados)
# ---------------------------------------------------------------------------
def parse_2016() -> list[dict[str, Any]]:
    soup = BeautifulSoup((HTML_DIR / "ciim_2016_cuadro_de_honor.html").read_text(encoding="utf-8"), "lxml")
    txt = soup.get_text("\n", strip=True)
    start = txt.find("PREMIAÇÃO")
    end = txt.find("Estamos en contacto")
    block = txt[start:end] if end > start else txt[start:]

    rows: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    current_prize = ""

    section_map = {
        "medalhas de ouro": "Medalha de Ouro",
        "medalhas de prata": "Medalha de Prata",
        "medalhas de bronze": "Medalha de Bronze",
        "mencoes honrosas": "Menção Honrosa",
    }

    for raw_line in block.splitlines():
        line = clean_text(raw_line)
        if not line or norm_key(line) == "premiacao":
            continue
        lk = norm_key(line)
        if lk in section_map:
            current_prize = section_map[lk]
            continue
        # Formato: "Nome - Universidade - País" (algumas linhas usam '–' ou '-México' sem espaço!)
        # Primeiro normaliza hífens separadores (cuidado com 'PUC - Rio' e 'EST/UEA')
        parts = re.split(r"\s*[-–]\s*(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ])", line)
        # Rejunta "PUC" + "Rio" se dividiu
        merged: list[str] = []
        for p in parts:
            if merged and merged[-1].upper() == "PUC" and p.strip().lower() == "rio":
                merged[-1] = "PUC - Rio"
            else:
                merged.append(p.strip())
        if len(merged) >= 3:
            name = merged[0]
            country = merged[-1]
            univ = " - ".join(merged[1:-1])
        elif len(merged) == 2:
            name, univ = merged[0], merged[1]
            country = infer_country_from_univ(univ)
        else:
            continue
        seen_keys.add(norm_key(name))
        rows.append(
            make_row(
                2016,
                **{
                    "Full name": name,
                    "University": univ,
                    "Country": country,
                    "Prize_raw": current_prize,
                },
            )
        )

    # Complementa com não-premiados de Concursantes-CIIM2016.pdf
    known_countries = [
        "México", "Mexico", "Brasil", "Brazil", "Colômbia", "Colombia",
        "Costa Rica", "Ecuador", "Equador", "Argentina", "Guatemala", "Perú", "Peru",
        "Venezuela", "Bolivia", "Honduras", "El Salvador", "España", "Espanha",
    ]
    country_re = re.compile(r"\b(" + "|".join(re.escape(c) for c in known_countries) + r")\s*$", re.I)

    with pdfplumber.open(PDF_DIR / "ciim_2016_concursantes_Concursantes-CIIM2016.pdf") as pdf:
        for page in pdf.pages:
            tbl = max(page.extract_tables(), key=len)
            for raw_c in tbl:
                c = [clean_text(x) for x in raw_c]
                if len(c) < 2 or not re.fullmatch(r"\d+", c[0]):
                    continue
                entry = c[1]
                # Extrair país do final
                m_co = country_re.search(entry)
                country = m_co.group(1) if m_co else ""
                body = entry[: m_co.start()].strip(" -–") if m_co else entry
                # Separar nome da universidade
                if " – " in body or " - " in body:
                    name, univ = re.split(r"\s+[-–]\s+", body, maxsplit=1)
                else:
                    m_u = re.search(
                        r"(?:\s+(Universidad|Universidade|IME\b|OBM\b|OMM\b|PUC|USP|UNICAMP|UFMG|CIMPA|CIMAT|ITCR|EST/UEA|UEA|Escuela|Instituto|TEC\b).*|(UEA))$",
                        body,
                    )
                    if m_u:
                        name = body[: m_u.start()].strip()
                        univ = body[m_u.start() :].strip()
                    else:
                        name, univ = body, ""
                nk = norm_key(name)
                if not nk or any(same_person_in_year(r["Full name"], name) for r in rows):
                    continue
                # Também checa sobreposição de >=2 tokens começando pelo mesmo primeiro nome
                ntoks = nk.split()
                if any(len(set(ntoks) & set(sk.split())) >= 2 and ntoks[0] == sk.split()[0] for sk in seen_keys):
                    continue
                seen_keys.add(nk)
                rows.append(
                    make_row(
                        2016,
                        **{
                            "Full name": name,
                            "University": univ,
                            "Country": country or infer_country_from_univ(univ),
                            "Prize_raw": "",
                        },
                    )
                )
    return rows


# ---------------------------------------------------------------------------
# 2017: Resultados-CIIM2017.pdf + medalhas/equipes das 5 imagens oficiais
# ---------------------------------------------------------------------------
TEAM_INFO_2017 = {
    "UBA": ("Universidad de Buenos Aires", "Argentina"),
    "OBR": ("Olimpiada Brasileira de Matemática", "Brasil"),
    "IME1": ("Instituto Militar de Engenharia", "Brasil"),
    "IME2": ("Instituto Militar de Engenharia", "Brasil"),
    "PUC": ("Pontifícia Universidade Católica do Rio de Janeiro", "Brasil"),
    "CIM": ("CIMPA - Universidad de Costa Rica", "Costa Rica"),
    "UCR": ("Universidad de Costa Rica", "Costa Rica"),
    "ITCR": ("Instituto Tecnológico de Costa Rica", "Costa Rica"),
    "USFQ": ("Universidad San Francisco de Quito", "Ecuador"),
    "OMEC": ("Olimpiada Matemática Ecuatoriana - OMEC", "Ecuador"),
    "OMM": ("Olimpiada Mexicana de Matemáticas", "México"),
    "UAQ": ("Universidad Autónoma de Querétaro", "México"),
    "UNAM": ("Universidad Nacional Autónoma de México", "México"),
    "UGU": ("Universidad de Guanajuato", "México"),
    "EPN": ("Escuela Politécnica Nacional", "Ecuador"),
    "UV": ("Universidad del Valle", "Colombia"),
    "UAN": ("Universidad Antonio Nariño", "Colombia"),
}

# Medalhas exatas lidas das 4 imagens CuadroHonorMedallas*-CIIM2017.jpg
AWARDS_2017: dict[str, str] = {
    # Oro (5)
    "oscar samuel henney arthur": "Medalla de Oro",
    "luize mello d urso vianna": "Medalla de Oro",
    "rafael kazuhiro miyazaki": "Medalla de Oro",
    "valentino amadeus sichinel": "Medalla de Oro",
    "humberto jimenez": "Medalla de Oro",
    # Plata (9)
    "lautaro decara": "Medalla de Plata",
    "thiago ribeiro tergolino": "Medalla de Plata",
    "lucas souza mota de aragao": "Medalla de Plata",
    "rafael filipe dos santos": "Medalla de Plata",
    "jorge fernandez hidalgo": "Medalla de Plata",
    "raphael mendes de oliveira": "Medalla de Plata",
    "luis felipe barquero jimenez": "Medalla de Plata",
    "jose ramon tuiran rangel": "Medalla de Plata",
    "harold steven erazo jimenez": "Medalla de Plata",
    # Bronce (15)
    "hector m de la rosa prado": "Medalla de Bronce",
    "ana karoline borges carneiro": "Medalla de Bronce",
    "joao baptista de paula e silva": "Medalla de Bronce",
    "joao babtista de paula e silva": "Medalla de Bronce",
    "miguel angel prado godoy": "Medalla de Bronce",
    "felipe magalhaes de matos gabriel": "Medalla de Bronce",
    "adrian delgado": "Medalla de Bronce",
    "kevin coto mora": "Medalla de Bronce",
    "axcel picado piedra": "Medalla de Bronce",
    "siddharta emmanuel morales guzman": "Medalla de Bronce",
    "sebastian lopez bolanos": "Medalla de Bronce",
    "owen yael mireles briones": "Medalla de Bronce",
    "abraham jaimes avila": "Medalla de Bronce",
    "melvin poveda": "Medalla de Bronce",
    "luis carlos garcia ramos": "Medalla de Bronce",
    "gerardo martin franco cordova": "Medalla de Bronce",
    # Menciones de Honor (14)
    "daniel de la riva massaad": "Mención de Honor",
    "roberto ferreira franco moura": "Mención de Honor",
    "william rodrigues machado": "Mención de Honor",
    "andres zamora nasralah": "Mención de Honor",
    "sofia garro carranza": "Mención de Honor",
    "roberto avalos": "Mención de Honor",
    "nicolas coloma": "Mención de Honor",
    "timothy bustillos": "Mención de Honor",
    "jose nain rivera robles": "Mención de Honor",
    "israel bonal rodriguez": "Mención de Honor",
    "german puga castillo": "Mención de Honor",
    "dario teran": "Mención de Honor",
    "anthony flores": "Mención de Honor",
    "santiago vela": "Mención de Honor",
}

# Os 16 participantes da página omitida entre UAQ2 e USFQ2 em Resultados-CIIM2017.pdf
# (extraídos de Concursantes-CIIM2017.jpg + CuadroHonor*-CIIM2017.jpg)
MISSING_FROM_PDF_2017 = [
    ("UBA1", "Lautaro Decara"),
    ("UCR1", "Andrés Zamora Nasralah"),
    ("UCR2", "Fernando Herrera"),
    ("UCR3", "Marco Josué Mejía Cerda"),
    ("UCR4", "Sebastián López Bolaños"),
    ("UAQ3", "Abraham Jaimes Avila"),
    ("UAQ4", "Luis Enrique Aguilar Díaz"),
    ("UNAM1", "Oscar Samuel Henney Arthur"),
    ("UNAM2", "Jorge Fernández Hidalgo"),
    ("UNAM3", "Gerardo Martín Franco Córdova"),
    ("UNAM4", "Siddharta Emmanuel Morales Guzmán"),
    ("UGU1", "Luis Carlos García Ramos"),
    ("UGU2", "Owen Yael Mireles Briones"),
    ("UGU3", "Miguel Ángel Prado Godoy"),
    ("UGU4", "Germán Puga Castillo"),
    ("USFQ1", "Roberto Avalos"),
]


def _team_info_2017(code: str) -> tuple[str, str]:
    prefix = re.sub(r"-\d+$", "", code)
    if prefix in TEAM_INFO_2017:
        return TEAM_INFO_2017[prefix]
    prefix2 = re.sub(r"\d+$", "", code)
    return TEAM_INFO_2017.get(prefix2, (code, ""))


def parse_2017() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with pdfplumber.open(PDF_DIR / "ciim_2017_resultados_Resultados-CIIM2017.pdf") as pdf:
        for page in pdf.pages:
            tbl = max(page.extract_tables(), key=len)
            for raw_c in tbl:
                c = [clean_text(x) for x in raw_c]
                if len(c) < 9 or norm_key(c[0]) == "equipo" or not re.fullmatch(r"\d+", c[8]):
                    continue
                univ, country = _team_info_2017(c[0])
                prize_raw = AWARDS_2017.get(norm_key(c[1]), "")
                rows.append(
                    make_row(
                        2017,
                        **{
                            "Code": c[0],
                            "Full name": c[1],
                            "University": univ,
                            "Country": country,
                            "P1": c[2], "P2": c[3], "P3": c[4], "P4": c[5], "P5": c[6], "P6": c[7],
                            "Total": c[8],
                            "Prize_raw": prize_raw,
                        },
                    )
                )

    for code, name in MISSING_FROM_PDF_2017:
        univ, country = _team_info_2017(code)
        prize_raw = AWARDS_2017.get(norm_key(name), "")
        rows.append(
            make_row(
                2017,
                **{
                    "Code": code,
                    "Full name": name,
                    "University": univ,
                    "Country": country,
                    "Prize_raw": prize_raw,
                },
            )
        )
    return rows


# ---------------------------------------------------------------------------
# 2018: HTML resultados (51 participantes) + cuadro_de_honor (cores de medalha)
# ---------------------------------------------------------------------------
def parse_2018() -> list[dict[str, Any]]:
    # 1. Mapa de medalhas por cor de fundo em ciim_2018_cuadro_de_honor.html
    s_ch = BeautifulSoup((HTML_DIR / "ciim_2018_cuadro_de_honor.html").read_text(encoding="utf-8"), "lxml")
    t_ch = max(s_ch.find_all("table"), key=lambda tb: len(tb.find_all("tr")))
    prize_by_name: dict[str, str] = {}
    color_map = {
        "#ffff66": "Medalla de Oro",
        "#cbd3d0": "Medalla de Plata",
        "#ee833a": "Medalla de Bronce",
    }
    for tr in t_ch.find_all("tr"):
        tds = tr.find_all(["td", "th"])
        if len(tds) < 4:
            continue
        name = clean_text(tds[0].get_text(" ", strip=True))
        if norm_key(name) == "nombre":
            continue
        style = (tds[0].get("style") or "").lower()
        prize = ""
        for hx, label in color_map.items():
            if hx in style:
                prize = label
                break
        if prize:
            prize_by_name[norm_key(name)] = prize

    # 2. Todos os 51 participantes de ciim_2018_resultados.html
    s_res = BeautifulSoup((HTML_DIR / "ciim_2018_resultados.html").read_text(encoding="utf-8"), "lxml")
    t_res = max(s_res.find_all("table"), key=lambda tb: len(tb.find_all("tr")))
    rows: list[dict[str, Any]] = []
    for tr in t_res.find_all("tr"):
        tds = tr.find_all(["td", "th"])
        if len(tds) < 4:
            continue
        c = [clean_text(td.get_text(" ", strip=True)) for td in tds]
        if norm_key(c[0]) == "nombre" or not re.fullmatch(r"\d+", c[3]):
            continue
        rows.append(
            make_row(
                2018,
                **{
                    "Full name": c[0],
                    "University": c[1],
                    "Country": c[2],
                    "Total": c[3],
                    "Prize_raw": prize_by_name.get(norm_key(c[0]), ""),
                },
            )
        )
    # Ordena por Total decrescente
    rows.sort(key=lambda r: (-int(r["Total"]) if r["Total"].isdigit() else 0, r["Full name"]))
    return rows


# ---------------------------------------------------------------------------
# 2019: Participantes-Medalleria-CIIM2019.pdf
# ---------------------------------------------------------------------------
def parse_2019() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with pdfplumber.open(PDF_DIR / "ciim_2019_medalleria_pdf.pdf") as pdf:
        for page in pdf.pages:
            tbl = max(page.extract_tables(), key=len)
            for raw_c in tbl:
                c = [clean_text(x) for x in raw_c]
                if len(c) < 12 or norm_key(c[0]).startswith("nombre") or not re.fullmatch(r"\d+", c[10]):
                    continue
                rows.append(
                    make_row(
                        2019,
                        **{
                            "First name": c[0],
                            "Family name": c[1],
                            "University": c[2],
                            "Country": c[3],
                            "P1": c[4], "P2": c[5], "P3": c[6], "P4": c[7], "P5": c[8], "P6": c[9],
                            "Total": c[10],
                            "Prize_raw": c[11],
                        },
                    )
                )
    return rows


# ---------------------------------------------------------------------------
# 2020: Medalleria-CIIM2020.pdf (65 premiados) + Participantes-CIIM2020.pdf
# ---------------------------------------------------------------------------
def parse_2020() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    with pdfplumber.open(PDF_DIR / "ciim_2020_medalleria_pdf.pdf") as pdf:
        for page in pdf.pages:
            tbl = max(page.extract_tables(), key=len)
            for raw_c in tbl:
                c = [clean_text(x) for x in raw_c]
                if len(c) < 12 or not re.fullmatch(r"\d+", c[0]):
                    continue
                fn, ln = c[1], c[2]
                if norm_key(fn) == norm_key(ln):
                    full = fn
                    fn, ln = "", ""
                else:
                    full = f"{fn} {ln}".strip()
                seen_keys.add(norm_key(full))
                rows.append(
                    make_row(
                        2020,
                        **{
                            "Pos": c[0],
                            "First name": fn,
                            "Family name": ln,
                            "Full name": full,
                            "University": c[3],
                            "Country": infer_country_from_univ(c[3]),
                            "P1": c[4], "P2": c[5], "P3": c[6], "P4": c[7], "P5": c[8], "P6": c[9],
                            "Total": c[10],
                            "Prize_raw": c[11],
                        },
                    )
                )

    # Complementa com os não-premiados de Participantes-CIIM2020.pdf (usando coords x/y por linha!)
    with pdfplumber.open(PDF_DIR / "ciim_2020_participantes_pdf.pdf") as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            by_y: dict[int, list[dict[str, Any]]] = {}
            for w in words:
                if w["top"] < 220:
                    continue
                ky = round(w["top"] / 4) * 4
                by_y.setdefault(ky, []).append(w)
            for ky in sorted(by_y):
                ws = sorted(by_y[ky], key=lambda w: w["x0"])
                if not ws or ws[0]["x0"] >= 145 or not re.fullmatch(r"\d+", ws[0]["text"]):
                    continue
                # Colunas confirmadas nas 4 páginas: x<145 (#), 145..260 (Nombres), 260..440 (Apellidos), >=440 (Institución)
                fn = " ".join(w["text"] for w in ws if 145 <= w["x0"] < 260).strip()
                ln = " ".join(w["text"] for w in ws if 260 <= w["x0"] < 440).strip()
                univ = " ".join(w["text"] for w in ws if w["x0"] >= 440).strip()
                if norm_key(fn) == norm_key(ln):
                    full = fn
                    fn, ln = "", ""
                else:
                    full = f"{fn} {ln}".strip()
                nk = norm_key(full)
                if not nk or any(same_person_in_year(r["Full name"], full) for r in rows):
                    continue
                seen_keys.add(nk)
                rows.append(
                    make_row(
                        2020,
                        **{
                            "First name": fn,
                            "Family name": ln,
                            "Full name": full,
                            "University": univ,
                            "Country": infer_country_from_univ(univ),
                            "Prize_raw": "",
                        },
                    )
                )
    return rows


# ---------------------------------------------------------------------------
# 2021: Medalleria.pdf (todos os 83 participantes numa única tabela!)
# ---------------------------------------------------------------------------
def parse_2021() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with pdfplumber.open(PDF_DIR / "ciim_2021_medalleria_pdf.pdf") as pdf:
        for page in pdf.pages:
            tbl = max(page.extract_tables(), key=len)
            for raw_c in tbl:
                c = [clean_text(x) for x in raw_c]
                if len(c) < 13 or not re.fullmatch(r"\d+", c[0]):
                    continue
                fn, ln = c[1], c[2]
                # Em 2021, linha 1 veio invertida ('Tostes Messias Pereira' / 'Gabriel')
                if norm_key(fn) == "tostes messias pereira" and norm_key(ln) == "gabriel":
                    fn, ln = ln, fn
                # Em 2021, 'Matheus Andrade Barreto' veio duplicado em Nombres e Apellidos
                if fn and ln and norm_key(fn) == norm_key(ln):
                    full, fn, ln = fn, "", ""
                else:
                    full = f"{fn} {ln}".strip()
                rows.append(
                    make_row(
                        2021,
                        **{
                            "Pos": c[0],
                            "First name": fn,
                            "Family name": ln,
                            "Full name": full,
                            "University": c[3],
                            "Country": c[4],
                            "P1": c[5], "P2": c[6], "P3": c[7], "P4": c[8], "P5": c[9], "P6": c[10],
                            "Total": c[11],
                            "Prize_raw": c[12],
                        },
                    )
                )
    return rows


# ---------------------------------------------------------------------------
# 2022: Medalleria.pdf (54 premiados)
# ---------------------------------------------------------------------------
def parse_2022() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with pdfplumber.open(PDF_DIR / "ciim_2022_medalleria_pdf.pdf") as pdf:
        for page in pdf.pages:
            tbl = max(page.extract_tables(), key=len)
            for raw_c in tbl:
                c = [clean_text(x) for x in raw_c]
                if len(c) < 6 or not re.fullmatch(r"\d+", c[4]):
                    continue
                rows.append(
                    make_row(
                        2022,
                        **{
                            "Country": c[0],
                            "University": c[1],
                            "First name": c[2],
                            "Family name": c[3],
                            "Total": c[4],
                            "Prize_raw": c[5],
                        },
                    )
                )
    return rows


# ---------------------------------------------------------------------------
# 2023: Resultados.pdf (págs 0 e 1, extração por palavras + faixas de prêmio)
# ---------------------------------------------------------------------------
def parse_2023() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    # Na XV CIIM 2023 (confirmado visualmente em 2023_p0.png e 2023_p1.png):
    # - Ouro: 48..39 | Prata: 37..26 | Bronze: 25..16
    # - Men Honrosa: explícito na coluna Premiação (x in [335, 400])
    with pdfplumber.open(PDF_DIR / "ciim_2023_resultados_Resultados.pdf") as pdf:
        for page in pdf.pages[:2]:
            words = page.extract_words()
            by_y: dict[int, list[dict[str, Any]]] = {}
            for w in words:
                ky = round(w["top"] / 4) * 4
                by_y.setdefault(ky, []).append(w)
            for ky in sorted(by_y):
                ws = sorted(by_y[ky], key=lambda w: w["x0"])
                nums = [w for w in ws if w["x0"] >= 402 and re.fullmatch(r"\d+", w["text"])]
                if len(nums) != 7:
                    continue
                name = " ".join(w["text"] for w in ws if w["x0"] < 210).strip()
                univ = " ".join(w["text"] for w in ws if 210 <= w["x0"] < 335).strip()
                prem_txt = " ".join(w["text"] for w in ws if 335 <= w["x0"] < 402).strip()
                p1, p2, p3, p4, p5, p6, tot_s = [w["text"] for w in nums]
                tot = int(tot_s)
                if tot >= 39:
                    prize_raw = "Ouro"
                elif tot >= 26:
                    prize_raw = "Prata"
                elif tot >= 16:
                    prize_raw = "Bronze"
                elif "honrosa" in prem_txt.lower():
                    prize_raw = "Menção Honrosa"
                else:
                    prize_raw = ""
                rows.append(
                    make_row(
                        2023,
                        **{
                            "Full name": name,
                            "University": univ,
                            "Country": infer_country_from_univ(univ),
                            "P1": p1, "P2": p2, "P3": p3, "P4": p4, "P5": p5, "P6": p6,
                            "Total": tot_s,
                            "Prize_raw": prize_raw,
                        },
                    )
                )
    return rows


# ---------------------------------------------------------------------------
# 2024: ResultadoPorEquipos.pdf (60 participantes c/ P1..P6) + Medallero.pdf
# ---------------------------------------------------------------------------
def parse_2024() -> list[dict[str, Any]]:
    # 1. Lê Medallero.pdf para obter Pos e Medalha/Mención de cada participante (1..60)
    pos_prize: dict[str, tuple[str, str]] = {}
    with pdfplumber.open(PDF_DIR / "ciim_2024_resultados_Medallero.pdf") as pdf:
        for page in pdf.pages:
            tbl = max(page.extract_tables(), key=len)
            for raw_c in tbl:
                c = [clean_text(x) for x in raw_c]
                if len(c) < 3 or not re.fullmatch(r"\d+", c[0]):
                    continue
                idx = int(c[0])
                name = c[1]
                col2 = c[2]
                if idx <= 6:
                    prize = "Medalla de Oro"
                elif idx <= 18:
                    prize = "Medalla de Plata"
                elif idx <= 33:
                    prize = "Medalla de Bronce"
                elif "menc" in norm_key(col2):
                    prize = "Mención Honorífica"
                else:
                    prize = ""
                pos_prize[norm_key(name)] = (str(idx), prize)

    # 2. Lê ResultadoPorEquipos.pdf (PAÍS, UNIVERSIDAD, NOMBRE, P1..P6, TOTAL)
    rows: list[dict[str, Any]] = []
    with pdfplumber.open(PDF_DIR / "ciim_2024_resultados_ResultadoPorEquipos.pdf") as pdf:
        for page in pdf.pages:
            tbl = max(page.extract_tables(), key=len)
            for raw_c in tbl:
                c = [clean_text(x) for x in raw_c]
                if len(c) < 10 or not re.fullmatch(r"\d+", c[9]):
                    continue
                nk = norm_key(c[2])
                pos, prize = pos_prize.get(nk, ("", ""))
                rows.append(
                    make_row(
                        2024,
                        **{
                            "Pos": pos,
                            "Country": c[0],
                            "University": c[1],
                            "Full name": c[2],
                            "P1": c[3], "P2": c[4], "P3": c[5], "P4": c[6], "P5": c[7], "P6": c[8],
                            "Total": c[9],
                            "Prize_raw": prize,
                        },
                    )
                )
    rows.sort(key=lambda r: (int(r["Pos"]) if r["Pos"].isdigit() else 999, r["Full name"]))
    return rows


# ---------------------------------------------------------------------------
# 2025: Resultados.pdf (60 participantes com rowspan em Premio) + Participantes.pdf
# ---------------------------------------------------------------------------
def parse_2025() -> list[dict[str, Any]]:
    # 1. Mapa de Equipo -> País via Participantes.pdf (2 colunas lado a lado)
    team_country: dict[str, str] = {}
    with pdfplumber.open(PDF_DIR / "ciim_2025_participantes_pdf.pdf") as pdf:
        tbl = max(pdf.pages[0].extract_tables(), key=len)
        for raw_c in tbl:
            c = [clean_text(x) for x in raw_c]
            if len(c) >= 2 and c[0] and c[1] and norm_key(c[0]) not in {"lider", "estudiante"}:
                team_country[norm_key(c[1])] = c[0]
            if len(c) >= 5 and c[3] and c[4] and norm_key(c[3]) not in {"lider", "estudiante"}:
                team_country[norm_key(c[4])] = c[3]

    # 2. Resultados.pdf: Premio None = célula mesclada (rowspan) com a de cima; '' = sem prêmio!
    rows: list[dict[str, Any]] = []
    last_prize = ""
    with pdfplumber.open(PDF_DIR / "ciim_2025_resultados_pdf.pdf") as pdf:
        for page in pdf.pages:
            tbl = max(page.extract_tables(), key=len)
            for raw_c in tbl:
                if len(raw_c) < 11:
                    continue
                pos = clean_text(raw_c[0])
                if not re.fullmatch(r"\d+", pos):
                    continue
                raw_prize_cell = raw_c[10]
                if raw_prize_cell is None:
                    prize_raw = last_prize
                else:
                    prize_raw = clean_text(raw_prize_cell)
                    last_prize = prize_raw
                team = clean_text(raw_c[1])
                country = team_country.get(norm_key(team)) or infer_country_from_univ(team)
                rows.append(
                    make_row(
                        2025,
                        **{
                            "Pos": pos,
                            "University": team,
                            "Country": country,
                            "Full name": clean_text(raw_c[2]),
                            "P1": raw_c[3], "P2": raw_c[4], "P3": raw_c[5],
                            "P4": raw_c[6], "P5": raw_c[7], "P6": raw_c[8],
                            "Total": raw_c[9],
                            "Prize_raw": prize_raw,
                        },
                    )
                )
    return rows


# ---------------------------------------------------------------------------
# 2026: Resultados.pdf (64 participantes com País, Código, P1..P6, Total, Medalla)
# ---------------------------------------------------------------------------
def parse_2026() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with pdfplumber.open(PDF_DIR / "ciim_2026_resultados_Resultados.pdf") as pdf:
        for page in pdf.pages:
            tbl = max(page.extract_tables(), key=len)
            for raw_c in tbl:
                c = [clean_text(x) for x in raw_c]
                if len(c) < 13 or not re.fullmatch(r"\d+", c[1]):
                    continue
                rows.append(
                    make_row(
                        2026,
                        **{
                            "Pos": c[1],
                            "Country": c[2],
                            "Code": c[3],
                            "Full name": c[4],
                            "P1": c[5], "P2": c[6], "P3": c[7], "P4": c[8], "P5": c[9], "P6": c[10],
                            "Total": c[11],
                            "Prize_raw": c[12],
                        },
                    )
                )
    return rows


PARSERS = {
    2009: parse_2009,
    2010: parse_2010,
    2011: parse_2011,
    2012: parse_2012,
    2013: parse_2013,
    2014: parse_2014,
    2015: parse_2015,
    2016: parse_2016,
    2017: parse_2017,
    2018: parse_2018,
    2019: parse_2019,
    2020: parse_2020,
    2021: parse_2021,
    2022: parse_2022,
    2023: parse_2023,
    2024: parse_2024,
    2025: parse_2025,
    2026: parse_2026,
}


def main() -> None:
    BY_YEAR_DIR.mkdir(parents=True, exist_ok=True)
    all_dfs: list[pd.DataFrame] = []
    for year in range(2009, 2027):
        rows = PARSERS[year]()
        df = pd.DataFrame(rows, columns=STANDARD_COLUMNS)
        out_path = BY_YEAR_DIR / f"ciim_results_{year}.csv"
        df.to_csv(out_path, index=False, encoding="utf-8")
        print(f"{year}: {len(df):3d} participantes -> {out_path.relative_to(ROOT_DIR)}", flush=True)
        all_dfs.append(df)

    all_df = pd.concat(all_dfs, ignore_index=True)
    all_path = OUTPUT_DIR / "ciim_results_all_years.csv"
    all_df.to_csv(all_path, index=False, encoding="utf-8")
    print(f"\nConsolidado CIIM salvo: {all_path.relative_to(ROOT_DIR)} ({len(all_df):,} linhas no total)")


if __name__ == "__main__":
    main()
