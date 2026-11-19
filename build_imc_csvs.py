"""Pipeline completo para gerar CSVs padronizados da IMC (1994-2026).

Fontes utilizadas (todas em cache local em files/imc/):
- 1994-1997: PDFs (files/imc/pdf/IMC_{year}_Results.pdf)
- 1998-2002: HTMLs salvos localmente (files/imc/html/{year}.html)
- 2003-2014: PDFs (files/imc/pdf/IMC_{year}_Results.pdf)
- 2015-2019: HTMLs salvos localmente (files/imc/html/{year}.html)
- 2020-2025: CSVs brutos extraídos do site antigo (files/imc/csv_raw/imc_results_{year}.csv)
- 2026:      PDF (files/imc/pdf/IMC_2026_Results.pdf)

Saídas:
- imc_results/imc_results_{year}.csv  (um CSV por ano, 1994 a 2026)
- imc_results/imc_results_all_years.csv (consolidado com todos os anos)
"""

from __future__ import annotations

import re
import subprocess
import unicodedata
from pathlib import Path
from typing import Any

import pandas as pd
import pdfplumber
import pymupdf
from bs4 import BeautifulSoup

HTML_DIR = Path("files/imc/html")
PDF_DIR = Path("files/imc/pdf")
CSV_RAW_DIR = Path("files/imc/csv_raw")
OUTPUT_DIR = Path("imc_results")

STANDARD_COLUMNS = [
    "Year",
    "Pos",
    "First name",
    "Family name",
    "Full name",
    "University",
    "Team",
    "City",
    "Country",
    "Code_D1",
    "D1_P1",
    "D1_P2",
    "D1_P3",
    "D1_P4",
    "D1_P5",
    "D1_P6",
    "Day1",
    "Code_D2",
    "D2_P1",
    "D2_P2",
    "D2_P3",
    "D2_P4",
    "D2_P5",
    "D2_P6",
    "Day2",
    "Sum",
    "Prize",
    "Prize_raw",
]


def clean_text(val: Any, join_hyphen: bool = False) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    s = str(val)
    # Remove soft hyphens, normalize special hyphens & ligatures
    s = s.replace("\xad", "").replace("\u2010", "-").replace("\xa0", " ")
    s = s.replace("ﬁ", "fi").replace("ﬂ", "fl").replace("ﬀ", "ff").replace("ﬃ", "ffi").replace("ﬄ", "ffl")
    if join_hyphen:
        s = re.sub(r"-\s*\n\s*", "-", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = unicodedata.normalize("NFC", s)
    return s


def clean_num(val: Any) -> str:
    s = clean_text(val)
    if not s or s in {"-", "–", "—", "nan", "None"}:
        return ""
    # Convert "10.0" -> "10", keep non-integer floats or strings like "disqualified"
    if re.fullmatch(r"-?\d+\.0+", s):
        return s.split(".")[0]
    return s


def normalize_prize(raw: str) -> str:
    s = clean_text(raw)
    if not s:
        return ""
    low = s.lower()
    if "withdrawn" in low:
        return "Withdrawn"
    if "disqualified" in low:
        return "Disqualified"
    if "grand grand" in low or "great grand" in low:
        return "Grand Grand First Prize"
    if "grand" in low and ("first" in low or "1st" in low):
        return "Grand First Prize"
    if "upper second" in low:
        return "Upper Second Prize"
    if "first" in low or low == "1st":
        return "First Prize"
    if "second" in low or low == "2nd":
        return "Second Prize"
    if "third" in low or low == "3rd":
        return "Third Prize"
    if "honourable" in low or "honorable" in low or "hon." in low or "hon men" in low or low in {"hm", "hon"}:
        return "Honourable Mention"
    if "special mention" in low:
        return "Special Mention"
    if "cert" in low:
        return "Certificate"
    return s


def make_row(year: int, **kwargs: Any) -> dict[str, Any]:
    row = {col: "" for col in STANDARD_COLUMNS}
    row["Year"] = year
    for k, v in kwargs.items():
        if k in row:
            row[k] = v
    # Ensure Full name is populated
    fn = clean_text(row["First name"])
    ln = clean_text(row["Family name"])
    full = clean_text(row["Full name"])
    if not full and (fn or ln):
        full = f"{fn} {ln}".strip()
    row["First name"] = fn
    row["Family name"] = ln
    row["Full name"] = full
    row["University"] = clean_text(row["University"])
    row["Team"] = clean_text(row["Team"])
    row["City"] = clean_text(row["City"])
    row["Country"] = clean_text(row["Country"])
    row["Pos"] = clean_text(row["Pos"]).rstrip(".")
    row["Prize_raw"] = clean_text(row["Prize_raw"] or row["Prize"])
    row["Prize"] = normalize_prize(row["Prize_raw"])
    for num_col in [
        "Code_D1", "D1_P1", "D1_P2", "D1_P3", "D1_P4", "D1_P5", "D1_P6", "Day1",
        "Code_D2", "D2_P1", "D2_P2", "D2_P3", "D2_P4", "D2_P5", "D2_P6", "Day2", "Sum",
    ]:
        row[num_col] = clean_num(row[num_col])
    return row


def expand_html_table(table) -> list[list[str]]:
    """Expande uma tabela HTML respeitando rowspan e colspan."""
    grid: list[list[str | None]] = []
    for r_idx, tr in enumerate(table.find_all("tr")):
        while len(grid) <= r_idx:
            grid.append([])
        c_idx = 0
        for cell in tr.find_all(["td", "th"]):
            while c_idx < len(grid[r_idx]) and grid[r_idx][c_idx] is not None:
                c_idx += 1
            rs = int(cell.get("rowspan") or 1)
            cs = int(cell.get("colspan") or 1)
            txt = clean_text(cell.get_text(" ", strip=True))
            for dr in range(rs):
                while len(grid) <= r_idx + dr:
                    grid.append([])
                row = grid[r_idx + dr]
                while len(row) < c_idx + cs:
                    row.append(None)
                for dc in range(cs):
                    row[c_idx + dc] = txt
            c_idx += cs
    return [[c if c is not None else "" for c in r] for r in grid]


def get_leaf_result_table(html_path: Path):
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8", errors="replace"), "lxml")
    candidates = [t for t in soup.find_all("table") if not t.find("table") and len(t.find_all("tr")) > 5]
    return max(candidates, key=lambda t: len(t.find_all("tr")))


# ---------------------------------------------------------------------------
# 1994 - 1997: PDFs listados por categoria de prêmio
# ---------------------------------------------------------------------------
def parse_1994_1997(year: int) -> list[dict[str, Any]]:
    pdf_path = PDF_DIR / f"IMC_{year}_Results.pdf"
    raw = subprocess.check_output(["pdftotext", "-layout", str(pdf_path), "-"]).decode("utf-8", errors="replace")
    lines = [clean_text(line) for line in raw.splitlines()]
    lines = [l for l in lines if l]

    prize_headers = {
        "grand first prize",
        "first prize",
        "upper second prize",
        "second prize",
        "third prize",
        "honourable mention",
        "honorable mention",
        "special mention",
        "certificate",
    }

    rows: list[dict[str, Any]] = []
    current_prize = ""
    for line in lines:
        if re.fullmatch(rf"{year}\s+results", line, flags=re.I):
            continue
        if line.lower() in prize_headers:
            current_prize = line
            continue
        if "," in line:
            full_name, univ = line.split(",", 1)
            rows.append(
                make_row(
                    year,
                    **{
                        "Full name": full_name.strip(),
                        "University": univ.strip(),
                        "Prize_raw": current_prize,
                    },
                )
            )
        else:
            # Em 1997 há 1 linha sem vírgula no PDF original: "Konstantin Andreev University of Sofia"
            m = re.match(r"^(.+?)\s+(University\b.+)$", line)
            if m:
                full_name, univ = m.group(1).strip(), m.group(2).strip()
            else:
                full_name, univ = line, ""
            rows.append(
                make_row(
                    year,
                    **{
                        "Full name": full_name,
                        "University": univ,
                        "Prize_raw": current_prize,
                    },
                )
            )
    return rows


# ---------------------------------------------------------------------------
# 1998: HTML local agrupado por seção de prêmio
# ---------------------------------------------------------------------------
def parse_1998() -> list[dict[str, Any]]:
    t = get_leaf_result_table(HTML_DIR / "1998.html")
    rows: list[dict[str, Any]] = []
    current_prize = ""
    for tr in t.find_all("tr"):
        cells = [clean_text(c.get_text(" ", strip=True)) for c in tr.find_all(["td", "th"])]
        if not any(cells):
            continue
        if len(cells) == 1:
            current_prize = cells[0]
            continue
        if cells[0].lower() == "name" and cells[1].lower() == "university":
            continue
        rows.append(
            make_row(
                1998,
                **{
                    "Full name": cells[0],
                    "University": cells[1] if len(cells) > 1 else "",
                    "Prize_raw": current_prize,
                },
            )
        )
    return rows


# ---------------------------------------------------------------------------
# 1999 - 2002: HTMLs locais com tabelas de notas
# ---------------------------------------------------------------------------
def parse_1999() -> list[dict[str, Any]]:
    t = get_leaf_result_table(HTML_DIR / "1999.html")
    rows: list[dict[str, Any]] = []
    for tr in t.find_all("tr"):
        c = [clean_text(td.get_text(" ", strip=True)) for td in tr.find_all(["td", "th"])]
        if len(c) < 20:
            continue
        if c[1].lower() == "name 1" or c[3].lower() == "average":
            continue
        rows.append(
            make_row(
                1999,
                **{
                    "Pos": c[0],
                    "First name": c[1],
                    "Family name": c[2],
                    "University": c[3],
                    "D1_P1": c[4], "D1_P2": c[5], "D1_P3": c[6], "D1_P4": c[7], "D1_P5": c[8], "D1_P6": c[9],
                    "Day1": c[10],
                    "D2_P1": c[11], "D2_P2": c[12], "D2_P3": c[13], "D2_P4": c[14], "D2_P5": c[15], "D2_P6": c[16],
                    "Day2": c[17],
                    "Sum": c[18],
                    "Prize_raw": c[19],
                },
            )
        )
    return rows


def parse_2000() -> list[dict[str, Any]]:
    t = get_leaf_result_table(HTML_DIR / "2000.html")
    rows: list[dict[str, Any]] = []
    for tr in t.find_all("tr"):
        c = [clean_text(td.get_text(" ", strip=True)) for td in tr.find_all(["td", "th"])]
        if len(c) < 21:
            continue
        if not c[0] or not re.match(r"^\d", c[0]):
            continue
        rows.append(
            make_row(
                2000,
                **{
                    "Pos": c[0],
                    "Full name": c[1],
                    "University": c[2],
                    "Code_D1": c[3],
                    "D1_P1": c[4], "D1_P2": c[5], "D1_P3": c[6], "D1_P4": c[7], "D1_P5": c[8], "D1_P6": c[9],
                    "Day1": c[10],
                    "Code_D2": c[11],
                    "D2_P1": c[12], "D2_P2": c[13], "D2_P3": c[14], "D2_P4": c[15], "D2_P5": c[16], "D2_P6": c[17],
                    "Day2": c[18],
                    "Sum": c[19],
                    "Prize_raw": c[20],
                },
            )
        )
    return rows


def parse_2001() -> list[dict[str, Any]]:
    t = get_leaf_result_table(HTML_DIR / "2001.html")
    rows: list[dict[str, Any]] = []
    for tr in t.find_all("tr"):
        c = [clean_text(td.get_text(" ", strip=True)) for td in tr.find_all(["td", "th"])]
        if len(c) < 17:
            continue
        if not c[0] or not re.match(r"^\d", c[0]):
            continue
        raw_name = c[1]
        if "," in raw_name:
            fam, fir = [p.strip() for p in raw_name.split(",", 1)]
        else:
            fir, fam = "", ""
        rows.append(
            make_row(
                2001,
                **{
                    "Pos": c[0],
                    "First name": fir,
                    "Family name": fam,
                    "Full name": f"{fir} {fam}".strip() if (fir or fam) else raw_name,
                    "University": c[2],
                    "D1_P1": c[3], "D1_P2": c[4], "D1_P3": c[5], "D1_P4": c[6], "D1_P5": c[7], "D1_P6": c[8],
                    "D2_P1": c[9], "D2_P2": c[10], "D2_P3": c[11], "D2_P4": c[12], "D2_P5": c[13], "D2_P6": c[14],
                    "Sum": c[15],
                    "Prize_raw": c[16],
                },
            )
        )
    return rows


def parse_2002() -> list[dict[str, Any]]:
    t = get_leaf_result_table(HTML_DIR / "2002.html")
    grid = expand_html_table(t)
    rows: list[dict[str, Any]] = []
    for c in grid:
        if len(c) < 23:
            continue
        if not c[1] or not re.match(r"^\d", c[1]):
            continue
        rows.append(
            make_row(
                2002,
                **{
                    "Pos": c[1],
                    "First name": c[2],
                    "Family name": c[3],
                    "University": c[4],
                    "Code_D1": c[5],
                    "D1_P1": c[6], "D1_P2": c[7], "D1_P3": c[8], "D1_P4": c[9], "D1_P5": c[10], "D1_P6": c[11],
                    "Day1": c[12],
                    "Code_D2": c[13],
                    "D2_P1": c[14], "D2_P2": c[15], "D2_P3": c[16], "D2_P4": c[17], "D2_P5": c[18], "D2_P6": c[19],
                    "Day2": c[20],
                    "Sum": c[21],
                    "Prize_raw": c[22],
                },
            )
        )
    return rows


# ---------------------------------------------------------------------------
# 2003 - 2007: PDFs com tabelas pdfplumber de 20/22/23 colunas
# ---------------------------------------------------------------------------
def parse_2003() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with pdfplumber.open(PDF_DIR / "IMC_2003_Results.pdf") as pdf:
        for page in pdf.pages:
            t = max(page.extract_tables(), key=len)
            for c in t:
                c = [clean_text(x) for x in c]
                if len(c) < 20:
                    continue
                if not c[0] or not re.match(r"^\d", c[0]):
                    continue
                rows.append(
                    make_row(
                        2003,
                        **{
                            "Pos": c[0],
                            "First name": c[1],
                            "Family name": c[2],
                            "University": c[3],
                            "D1_P1": c[4], "D1_P2": c[5], "D1_P3": c[6], "D1_P4": c[7], "D1_P5": c[8], "D1_P6": c[9],
                            "Day1": c[10],
                            "D2_P1": c[11], "D2_P2": c[12], "D2_P3": c[13], "D2_P4": c[14], "D2_P5": c[15], "D2_P6": c[16],
                            "Day2": c[17],
                            "Sum": c[18],
                            "Prize_raw": c[19],
                        },
                    )
                )
    return rows


def parse_2004_2007(year: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 1 if year == 2005 else 0
    with pdfplumber.open(PDF_DIR / f"IMC_{year}_Results.pdf") as pdf:
        for page in pdf.pages:
            t = max(page.extract_tables(), key=len)
            for raw_c in t:
                c = [clean_text(x) for x in raw_c[offset:]]
                if len(c) < 22:
                    continue
                if not c[0] or not re.match(r"^\d", c[0]):
                    continue
                rows.append(
                    make_row(
                        year,
                        **{
                            "Pos": c[0],
                            "First name": c[1],
                            "Family name": c[2],
                            "University": c[3],
                            "Code_D1": c[4],
                            "D1_P1": c[5], "D1_P2": c[6], "D1_P3": c[7], "D1_P4": c[8], "D1_P5": c[9], "D1_P6": c[10],
                            "Day1": c[11],
                            "Code_D2": c[12],
                            "D2_P1": c[13], "D2_P2": c[14], "D2_P3": c[15], "D2_P4": c[16], "D2_P5": c[17], "D2_P6": c[18],
                            "Day2": c[19],
                            "Sum": c[20],
                            "Prize_raw": c[21],
                        },
                    )
                )
    return rows


# ---------------------------------------------------------------------------
# 2008: PDF com spans PyMuPDF (evita overflow de University sobre Nr/P1..P3)
# ---------------------------------------------------------------------------
def parse_2008() -> list[dict[str, Any]]:
    # Limites x0 calibrados a partir das colunas exatas do PDF de 2008
    col_bounds = [
        ("Pos", 0, 39.5),
        ("First name", 39.5, 90.0),
        ("Family name", 90.0, 151.5),
        ("University", 151.5, 274.5),
        ("Code_D1", 274.5, 289.5),
        ("D1_P1", 289.5, 300.5),
        ("D1_P2", 300.5, 311.0),
        ("D1_P3", 311.0, 321.5),
        ("D1_P4", 321.5, 332.0),
        ("D1_P5", 332.0, 342.5),
        ("D1_P6", 342.5, 353.0),
        ("Day1", 353.0, 366.5),
        ("Code_D2", 366.5, 381.5),
        ("D2_P1", 381.5, 392.5),
        ("D2_P2", 392.5, 403.0),
        ("D2_P3", 403.0, 413.5),
        ("D2_P4", 413.5, 424.0),
        ("D2_P5", 424.0, 434.5),
        ("D2_P6", 434.5, 445.5),
        ("Day2", 445.5, 462.5),
        ("Sum", 462.5, 479.0),
        ("Prize_raw", 479.0, 999.0),
    ]

    def assign_col(x0: float) -> str:
        for name, lo, hi in col_bounds:
            if lo <= x0 < hi:
                return name
        return "Prize_raw"

    rows: list[dict[str, Any]] = []
    doc = pymupdf.open(PDF_DIR / "IMC_2008_Results.pdf")
    for page in doc:
        # Coleta todos os spans sem clipping
        spans = []
        for b in page.get_text("dict", flags=0)["blocks"]:
            for l in b.get("lines", []):
                for s in l["spans"]:
                    txt = s["text"].strip()
                    if not txt:
                        continue
                    spans.append((s["bbox"][0], s["bbox"][1], txt))
        # Agrupa spans por linha y (tolerância 3pt)
        spans.sort(key=lambda item: (item[1], item[0]))
        lines_grouped: list[tuple[float, list[tuple[float, float, str]]]] = []
        for sp in spans:
            if not lines_grouped or abs(sp[1] - lines_grouped[-1][0]) > 3.5:
                lines_grouped.append((sp[1], [sp]))
            else:
                lines_grouped[-1][1].append(sp)

        for _, lspans in lines_grouped:
            rec: dict[str, list[str]] = {}
            for x0, _, txt in sorted(lspans, key=lambda s: s[0]):
                col = assign_col(x0)
                # Em 2008 às vezes Pos e First name vêm grudados no mesmo span (ex: '279Elizaveta')
                if col == "Pos":
                    m = re.match(r"^(\d+)\s*(.+)$", txt)
                    if m and not m.group(2).isdigit():
                        rec.setdefault("Pos", []).append(m.group(1))
                        rec.setdefault("First name", []).append(m.group(2))
                        continue
                rec.setdefault(col, []).append(txt)
            pos = " ".join(rec.get("Pos", [])).strip()
            if not pos or not re.fullmatch(r"\d+", pos):
                continue
            joined = {k: " ".join(v).strip() for k, v in rec.items()}
            rows.append(make_row(2008, **joined))
    return rows


# ---------------------------------------------------------------------------
# 2009 - 2010: PDFs pdfplumber (19 cols) + Prize à direita via bbox da linha
# ---------------------------------------------------------------------------
def parse_2009_2010(year: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with pdfplumber.open(PDF_DIR / f"IMC_{year}_Results.pdf") as pdf:
        for page in pdf.pages:
            tables = page.find_tables()
            if not tables:
                continue
            tbl = max(tables, key=lambda t: len(t.rows))
            extracted = tbl.extract()
            right_x = tbl.bbox[2]
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            right_words = [w for w in words if w["x0"] >= right_x - 3]

            for r_obj, cells in zip(tbl.rows, extracted):
                c = [clean_text(x) for x in cells]
                if len(c) < 19:
                    continue
                if not c[0] or not re.match(r"^\d", c[0]):
                    continue
                y0, y1 = r_obj.bbox[1], r_obj.bbox[3]
                p_words = [
                    w for w in right_words
                    if (y0 - 2) <= ((w["top"] + w["bottom"]) / 2.0) <= (y1 + 2)
                ]
                p_words.sort(key=lambda w: (round(w["top"], 1), w["x0"]))
                prize_raw = " ".join(w["text"] for w in p_words).strip()

                rows.append(
                    make_row(
                        year,
                        **{
                            "Pos": c[0],
                            "First name": c[1],
                            "Family name": c[2],
                            "University": c[3],
                            "Code_D1": c[4],
                            "D1_P1": c[5], "D1_P2": c[6], "D1_P3": c[7], "D1_P4": c[8], "D1_P5": c[9],
                            "Day1": c[10],
                            "Code_D2": c[11],
                            "D2_P1": c[12], "D2_P2": c[13], "D2_P3": c[14], "D2_P4": c[15], "D2_P5": c[16],
                            "Day2": c[17],
                            "Sum": c[18],
                            "Prize_raw": prize_raw,
                        },
                    )
                )
    return rows


# ---------------------------------------------------------------------------
# 2011 e 2013: PDFs de 6 colunas via pdfplumber
# ---------------------------------------------------------------------------
def parse_2011() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with pdfplumber.open(PDF_DIR / "IMC_2011_Results.pdf") as pdf:
        for page in pdf.pages:
            t = max(page.extract_tables(), key=len)
            for raw_c in t:
                c = [clean_text(x) for x in raw_c]
                if len(c) < 6 or not c[0] or not re.match(r"^\d", c[0]):
                    continue
                rows.append(
                    make_row(
                        2011,
                        **{
                            "Pos": c[0],
                            "First name": c[1],
                            "Family name": c[2],
                            "University": c[3],
                            "Sum": c[4],
                            "Prize_raw": c[5],
                        },
                    )
                )
    return rows


def parse_2013() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with pdfplumber.open(PDF_DIR / "IMC_2013_Results.pdf") as pdf:
        for page in pdf.pages:
            t = max(page.extract_tables(), key=len)
            for raw_c in t:
                c = [clean_text(x) for x in raw_c]
                if len(c) < 6 or not c[0] or not re.match(r"^\d", c[0]):
                    continue
                rows.append(
                    make_row(
                        2013,
                        **{
                            "Pos": c[0],
                            "First name": c[1],
                            "Family name": c[2],
                            "University": c[3],
                            "Team": c[4],
                            "Prize_raw": c[5],
                        },
                    )
                )
    return rows


# ---------------------------------------------------------------------------
# 2012: PDF rotacionado 90° com spans não-clippados (PyMuPDF flags=0)
# ---------------------------------------------------------------------------
def parse_2012() -> list[dict[str, Any]]:
    # No PDF rotacionado 90° de 2012:
    # - bbox[0] (raw x0) identifica a LINHA da tabela (cresce de cima para baixo)
    # - bbox[3] (raw y1, início visual da célula) identifica a COLUNA (decresce da esquerda para a direita!)
    # Calibrado a partir dos spans de cabeçalho/dados de 2012:
    #   Pos: y1 >= 726
    #   First name: 649 <= y1 < 726
    #   Family name: 552 <= y1 < 649
    #   University: 445.5 <= y1 < 552 (mesmo quando transborda à direita, seu y1 inicial é ~550.5!)
    #   Code_D1: 427 <= y1 < 445.5
    #   D1_P1..P5: ~422, ~402, ~383, ~363, ~343
    #   Day1: ~325
    #   Code_D2: ~306
    #   D2_P1..P5: ~284, ~265, ~245, ~225, ~205
    #   Day2: ~187
    #   Sum: ~160
    #   Prize: y1 < 142
    col_ranges = [
        ("Pos", 726.0, 999.0),
        ("First name", 649.0, 726.0),
        ("Family name", 552.0, 649.0),
        ("University", 445.5, 552.0),
        ("Code_D1", 426.0, 445.5),
        ("D1_P1", 408.0, 426.0),
        ("D1_P2", 388.0, 408.0),
        ("D1_P3", 368.0, 388.0),
        ("D1_P4", 348.0, 368.0),
        ("D1_P5", 329.0, 348.0),
        ("Day1", 310.0, 329.0),
        ("Code_D2", 289.0, 310.0),
        ("D2_P1", 270.0, 289.0),
        ("D2_P2", 250.0, 270.0),
        ("D2_P3", 230.0, 250.0),
        ("D2_P4", 210.0, 230.0),
        ("D2_P5", 191.0, 210.0),
        ("Day2", 168.0, 191.0),
        ("Sum", 142.0, 168.0),
        ("Prize_raw", 0.0, 142.0),
    ]

    def assign_col(y1: float) -> str:
        for name, lo, hi in col_ranges:
            if lo <= y1 < hi:
                return name
        return "Prize_raw"

    rows: list[dict[str, Any]] = []
    doc = pymupdf.open(PDF_DIR / "IMC_2012_Results.pdf")
    for page in doc:
        spans = []
        for b in page.get_text("dict", flags=0)["blocks"]:
            for l in b.get("lines", []):
                for s in l["spans"]:
                    txt = s["text"].strip()
                    if not txt:
                        continue
                    # bbox = (x0, y0, x1, y1); row coord = x0, visual-left = y1
                    spans.append((s["bbox"][0], s["bbox"][3], txt))
        spans.sort(key=lambda item: (item[0], -item[1]))
        grouped: list[tuple[float, list[tuple[float, float, str]]]] = []
        for sp in spans:
            if not grouped or abs(sp[0] - grouped[-1][0]) > 4.5:
                grouped.append((sp[0], [sp]))
            else:
                grouped[-1][1].append(sp)

        for _, lspans in grouped:
            rec: dict[str, list[str]] = {}
            for _, y1, txt in sorted(lspans, key=lambda s: -s[1]):
                col = assign_col(y1)
                rec.setdefault(col, []).append(txt)
            pos = " ".join(rec.get("Pos", [])).strip()
            if not pos or not re.fullmatch(r"\d+", pos):
                continue
            joined = {k: " ".join(v).strip() for k, v in rec.items()}
            rows.append(make_row(2012, **joined))
    return rows


# ---------------------------------------------------------------------------
# 2014: PDF de 20 colunas via pdfplumber
# ---------------------------------------------------------------------------
def parse_2014() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with pdfplumber.open(PDF_DIR / "IMC_2014_Results.pdf") as pdf:
        for page in pdf.pages:
            t = max(page.extract_tables(), key=len)
            for raw_c in t:
                c = [clean_text(x, join_hyphen=True) for x in raw_c]
                if len(c) < 20 or not c[0] or not re.match(r"^\d", c[0]):
                    continue
                rows.append(
                    make_row(
                        2014,
                        **{
                            "Pos": c[0],
                            "First name": c[1],
                            "Family name": c[2],
                            "University": c[3],
                            "Code_D1": c[4],
                            "D1_P1": c[5], "D1_P2": c[6], "D1_P3": c[7], "D1_P4": c[8], "D1_P5": c[9],
                            "Day1": c[10],
                            "Code_D2": c[11],
                            "D2_P1": c[12], "D2_P2": c[13], "D2_P3": c[14], "D2_P4": c[15], "D2_P5": c[16],
                            "Day2": c[17],
                            "Sum": c[18],
                            "Prize_raw": c[19],
                        },
                    )
                )
    return rows


# ---------------------------------------------------------------------------
# 2015 - 2019: HTMLs locais modernos v1
# ---------------------------------------------------------------------------
def parse_2015_2019(year: int) -> list[dict[str, Any]]:
    t = get_leaf_result_table(HTML_DIR / f"{year}.html")
    rows: list[dict[str, Any]] = []
    for tr in t.find_all("tr"):
        c = [clean_text(td.get_text(" ", strip=True)) for td in tr.find_all(["td", "th"])]
        if len(c) < 18:
            continue
        if c[0].lower() == "pos" or c[1].lower() == "first name":
            continue
        # Tratar caso especial 2018 disqualified: len=19 onde c[16]='disqualified', c[17]='', c[18]='disqualified'
        prize_raw = c[17]
        if not prize_raw and len(c) > 18 and c[18]:
            prize_raw = c[18]
        rows.append(
            make_row(
                year,
                **{
                    "Pos": c[0],
                    "First name": c[1],
                    "Family name": c[2],
                    "University": c[3],
                    "D1_P1": c[4], "D1_P2": c[5], "D1_P3": c[6], "D1_P4": c[7], "D1_P5": c[8],
                    "Day1": c[9],
                    "D2_P1": c[10], "D2_P2": c[11], "D2_P3": c[12], "D2_P4": c[13], "D2_P5": c[14],
                    "Day2": c[15],
                    "Sum": c[16],
                    "Prize_raw": prize_raw,
                },
            )
        )
    return rows


# ---------------------------------------------------------------------------
# 2020 - 2025: CSVs brutos salvos localmente (extraídos do HTML original)
# ---------------------------------------------------------------------------
def parse_2020_2025(year: int) -> list[dict[str, Any]]:
    df = pd.read_csv(CSV_RAW_DIR / f"imc_results_{year}.csv", dtype=str).fillna("")
    rows: list[dict[str, Any]] = []
    four_probs = year in {2020, 2021, 2022}
    for _, r in df.iterrows():
        kwargs: dict[str, Any] = {
            "Pos": r.get("Pos", ""),
            "First name": r.get("First name", ""),
            "Family name": r.get("Family name", ""),
            "University": r.get("University", ""),
            "City": r.get("City", ""),
            "Country": r.get("Country", ""),
            "Day1": r.get("Day1", ""),
            "Day2": r.get("Day2", ""),
            "Sum": r.get("Sum", ""),
            "Prize_raw": r.get("Prize", ""),
        }
        if four_probs:
            kwargs.update({
                "D1_P1": r.get("P1", ""), "D1_P2": r.get("P2", ""), "D1_P3": r.get("P3", ""), "D1_P4": r.get("P4", ""),
                "D2_P1": r.get("P5", ""), "D2_P2": r.get("P6", ""), "D2_P3": r.get("P7", ""), "D2_P4": r.get("P8", ""),
            })
        else:
            kwargs.update({
                "D1_P1": r.get("P1", ""), "D1_P2": r.get("P2", ""), "D1_P3": r.get("P3", ""), "D1_P4": r.get("P4", ""), "D1_P5": r.get("P5", ""),
                "D2_P1": r.get("P6", ""), "D2_P2": r.get("P7", ""), "D2_P3": r.get("P8", ""), "D2_P4": r.get("P9", ""), "D2_P5": r.get("P10", ""),
            })
        rows.append(make_row(year, **kwargs))
    return rows


# ---------------------------------------------------------------------------
# 2026: PDF geométrico usando linhas horizontais pretas + cortes x exatos
# ---------------------------------------------------------------------------
def parse_2026() -> list[dict[str, Any]]:
    col_bounds = [
        ("Pos", 0.0, 74.5),
        ("First name", 74.5, 179.5),
        ("Family name", 179.5, 287.5),
        ("University", 287.5, 413.5),
        ("City", 413.5, 491.5),
        ("D1_P1", 491.5, 507.0),
        ("D1_P2", 507.0, 522.2),
        ("D1_P3", 522.2, 537.4),
        ("D1_P4", 537.4, 552.8),
        ("D1_P5", 552.8, 568.2),
        ("Day1", 568.2, 596.2),
        ("D2_P1", 596.2, 611.5),
        ("D2_P2", 611.5, 626.6),
        ("D2_P3", 626.6, 641.8),
        ("D2_P4", 641.8, 657.2),
        ("D2_P5", 657.2, 678.9),
        ("Day2", 678.9, 706.8),
        ("Sum", 706.8, 731.5),
        ("Prize_raw", 731.5, 999.0),
    ]

    def assign_col(xc: float) -> str:
        for name, lo, hi in col_bounds:
            if lo <= xc < hi:
                return name
        return "Prize_raw"

    def join_cell_words(wlist: list[dict[str, Any]], col: str) -> str:
        if not wlist:
            return ""
        # Agrupa por linha visual dentro da célula
        wlist = sorted(wlist, key=lambda w: (w["top"], w["x0"]))
        lines: list[list[dict[str, Any]]] = []
        for w in wlist:
            if not lines or abs(w["top"] - lines[-1][0]["top"]) > 4.0:
                lines.append([w])
            else:
                lines[-1].append(w)
        line_strs = [" ".join(w["text"] for w in sorted(ln, key=lambda w: w["x0"])) for ln in lines]
        if col == "Pos":
            # "10–" + "12." -> "10–12."
            joined = "".join(line_strs)
            return clean_text(joined)
        # Juntar com \n e deixar clean_text(join_hyphen=True) unir hífens de quebra de linha
        return clean_text("\n".join(line_strs), join_hyphen=True)

    rows: list[dict[str, Any]] = []
    with pdfplumber.open(PDF_DIR / "IMC_2026_Results.pdf") as pdf:
        for page in pdf.pages:
            # Linhas horizontais pretas definem exatamente cada faixa de linha
            hlines = sorted(
                set(
                    round(r["top"], 1)
                    for r in page.rects
                    if r["height"] <= 1.5 and r["width"] > 50 and r.get("non_stroking_color") == 0.0
                )
            )
            # Deduplicar hlines muito próximas (< 4pt)
            dedup: list[float] = []
            for y in hlines:
                if not dedup or y - dedup[-1] > 4.0:
                    dedup.append(y)
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            for y_top, y_bot in zip(dedup[:-1], dedup[1:]):
                band_words = [
                    w for w in words
                    if y_top <= ((w["top"] + w["bottom"]) / 2.0) <= y_bot
                ]
                if not band_words:
                    continue
                by_col: dict[str, list[dict[str, Any]]] = {}
                for w in band_words:
                    xc = (w["x0"] + w["x1"]) / 2.0
                    col = assign_col(xc)
                    by_col.setdefault(col, []).append(w)
                pos = join_cell_words(by_col.get("Pos", []), "Pos")
                if not pos or pos.lower() == "pos" or not re.match(r"^\d", pos):
                    continue
                rec = {col: join_cell_words(wlist, col) for col, wlist in by_col.items()}
                rows.append(make_row(2026, **rec))
    return rows


def parse_year(year: int) -> list[dict[str, Any]]:
    if 1994 <= year <= 1997:
        return parse_1994_1997(year)
    if year == 1998:
        return parse_1998()
    if year == 1999:
        return parse_1999()
    if year == 2000:
        return parse_2000()
    if year == 2001:
        return parse_2001()
    if year == 2002:
        return parse_2002()
    if year == 2003:
        return parse_2003()
    if 2004 <= year <= 2007:
        return parse_2004_2007(year)
    if year == 2008:
        return parse_2008()
    if year in {2009, 2010}:
        return parse_2009_2010(year)
    if year == 2011:
        return parse_2011()
    if year == 2012:
        return parse_2012()
    if year == 2013:
        return parse_2013()
    if year == 2014:
        return parse_2014()
    if 2015 <= year <= 2019:
        return parse_2015_2019(year)
    if 2020 <= year <= 2025:
        return parse_2020_2025(year)
    if year == 2026:
        return parse_2026()
    raise ValueError(f"Ano não suportado: {year}")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    all_dfs: list[pd.DataFrame] = []
    for year in range(1994, 2027):
        rows = parse_year(year)
        df = pd.DataFrame(rows, columns=STANDARD_COLUMNS)
        out_path = OUTPUT_DIR / f"imc_results_{year}.csv"
        df.to_csv(out_path, index=False, encoding="utf-8")
        print(f"{year}: {len(df):4d} participantes -> {out_path}", flush=True)
        all_dfs.append(df)

    all_df = pd.concat(all_dfs, ignore_index=True)
    all_path = OUTPUT_DIR / "imc_results_all_years.csv"
    all_df.to_csv(all_path, index=False, encoding="utf-8")
    print(f"\nConsolidado salvo: {all_path} ({len(all_df):,} linhas no total)")


if __name__ == "__main__":
    main()
