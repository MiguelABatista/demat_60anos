"""Pipeline completo para gerar CSVs padronizados da IMC (1994-2026).

Fontes utilizadas (em cache local em data/raw/):
- 1994-1997: PDFs (data/raw/pdf/IMC_{year}_Results.pdf)
- 1998-2002: HTMLs salvos localmente (data/raw/html/{year}.html)
- 2003-2014: PDFs (data/raw/pdf/IMC_{year}_Results.pdf)
- 2015-2019: HTMLs salvos localmente (data/raw/html/{year}.html)
- 2020-2025: CSVs brutos extraídos do site antigo (data/raw/csv_raw/imc_results_{year}.csv)
- 2026:      PDF (data/raw/pdf/IMC_2026_Results.pdf)

Saídas:
- data/processed/by_year/imc_results_{year}.csv  (um CSV por ano, 1994 a 2026)
- data/processed/imc_results_all_years.csv       (consolidado com todos os anos)
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

ROOT_DIR = Path(__file__).resolve().parent.parent
HTML_DIR = ROOT_DIR / "data" / "raw" / "html"
PDF_DIR = ROOT_DIR / "data" / "raw" / "pdf"
CSV_RAW_DIR = ROOT_DIR / "data" / "raw" / "csv_raw"
OUTPUT_DIR = ROOT_DIR / "data" / "processed"
BY_YEAR_DIR = OUTPUT_DIR / "by_year"

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
# Helper unificado para PDFs tabulares horizontais (2003-2008, 2013, 2014):
# usa geometria (linhas/colunas) do pdfplumber + spans não-clippados do PyMuPDF
# para evitar 100% de intercalação de texto quando uma célula transborda!
# ---------------------------------------------------------------------------
def _split_chars_at_boundary(chars: list[dict[str, Any]], boundary_x: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Divide uma lista de chars em torno de boundary_x, evitando cortar a última letra
    minúscula antes de uma maiúscula quando duas células se encostam sem espaço."""
    split_i = len(chars)
    for i, ch in enumerate(chars):
        cxc = (ch["bbox"][0] + ch["bbox"][2]) / 2.0
        if cxc >= boundary_x - 1.0:
            split_i = i
            break
    if 0 < split_i < len(chars) and chars[split_i]["c"].islower():
        for j in range(split_i, min(len(chars), split_i + 5)):
            if chars[j]["c"] == " ":
                split_i = j + 1
                break
            if chars[j]["c"].isupper() and j > 0 and chars[j - 1]["c"].islower():
                split_i = j
                break
    return chars[:split_i], chars[split_i:]


def _join_col_spans(items: list[tuple[float, float, float, str]], join_hyphen: bool = False) -> str:
    """Concatena spans da mesma coluna preservando quebras de linha e unindo sem espaço
    fragmentos colados na mesma linha (ex: 'Micha' + 'ł' + 'ek' -> 'Michałek')."""
    if not items:
        return ""
    items = sorted(items, key=lambda s: (s[1], s[0]))
    lines: list[list[tuple[float, float, float, str]]] = []
    for sp in items:
        if not lines or abs(sp[1] - lines[-1][0][1]) > 4.0:
            lines.append([sp])
        else:
            lines[-1].append(sp)
    line_strs: list[str] = []
    for ln in lines:
        ln.sort(key=lambda s: s[0])
        out = ""
        prev_x1: float | None = None
        for x0, _, x1, txt in ln:
            if prev_x1 is not None and (x0 - prev_x1) >= 1.2 and not out.endswith(" ") and not txt.startswith(" "):
                out += " "
            out += txt
            prev_x1 = x1
        line_strs.append(out.strip())
    sep = "\n" if join_hyphen else " "
    return clean_text(sep.join(line_strs), join_hyphen=join_hyphen)


def extract_pdf_table_unclipped(
    pdf_path: Path,
    year: int,
    col_names: list[str],
    col_offset: int = 0,
    join_hyphen: bool = False,
) -> list[dict[str, Any]]:
    n_cols = len(col_names)
    num_start_idx = next(
        (i for i, name in enumerate(col_names) if name in {"Code_D1", "D1_P1", "Sum"}),
        n_cols,
    )
    univ_idx = col_names.index("University") if "University" in col_names else -1
    prize_idx = col_names.index("Prize_raw") if "Prize_raw" in col_names else -1

    flags = pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_CLIP
    rows: list[dict[str, Any]] = []
    doc = pymupdf.open(pdf_path)

    with pdfplumber.open(pdf_path) as pdf:
        for ppage, mpage in zip(pdf.pages, doc):
            tables = ppage.find_tables()
            if not tables:
                continue
            tbl = max(tables, key=lambda t: len(t.rows))
            if len(tbl.columns) < col_offset + n_cols:
                continue

            col_xs: list[tuple[float, float]] = []
            for c_idx in range(col_offset, col_offset + n_cols):
                col_cells = [cell for cell in tbl.columns[c_idx].cells if cell is not None]
                narrowest = min(col_cells, key=lambda c: c[2] - c[0])
                col_xs.append((narrowest[0], narrowest[2]))

            def col_idx_for_x(x: float) -> int:
                if prize_idx >= 0 and x >= col_xs[prize_idx][0] - 1.5:
                    return prize_idx
                for idx, (cx0, cx1) in enumerate(col_xs):
                    if cx0 - 1.5 <= x < cx1 - 0.5:
                        return idx
                return min(range(n_cols), key=lambda i: abs(x - col_xs[i][0]))

            raw_spans = []
            for b in mpage.get_text("rawdict", flags=flags)["blocks"]:
                for l in b.get("lines", []):
                    for s in l["spans"]:
                        chars = s.get("chars", [])
                        non_ws = [ch for ch in chars if not ch["c"].isspace()]
                        if not non_ws:
                            continue
                        # Recorta espaços das pontas para usar o bbox real do texto visível
                        first_i = chars.index(non_ws[0])
                        last_i = len(chars) - 1 - list(reversed(chars)).index(non_ws[-1])
                        trimmed = chars[first_i : last_i + 1]
                        txt = "".join(ch["c"] for ch in trimmed)
                        x0 = trimmed[0]["bbox"][0]
                        x1 = trimmed[-1]["bbox"][2]
                        y0, y1 = s["bbox"][1], s["bbox"][3]
                        raw_spans.append((x0, (y0 + y1) / 2.0, x1, txt, trimmed))

            for r_obj in tbl.rows:
                c0 = r_obj.cells[col_offset] if len(r_obj.cells) > col_offset else None
                if c0 is None:
                    continue
                ry0, ry1 = c0[1], c0[3]
                if (ry1 - ry0) > 80:
                    continue

                # Estritamente dentro de [ry0, ry1) evita pegar spans da linha adjacente
                row_spans = [sp for sp in raw_spans if ry0 <= sp[1] < ry1]
                if not row_spans:
                    continue

                rec: dict[str, list[tuple[float, float, float, str]]] = {}
                overflow_candidates: list[tuple[int, float, float, float, list[dict[str, Any]]]] = []

                for x0, yc, x1, txt, chars in sorted(row_spans, key=lambda s: (round(s[1], 1), s[0])):
                    start_idx = col_idx_for_x(x0)

                    # Prize_raw: manter span inteiro
                    if start_idx == prize_idx:
                        rec.setdefault("Prize_raw", []).append((x0, yc, x1, txt))
                        continue

                    # Pos: pode vir grudado com First name (ex: '2 Przemyslaw', '279Elizaveta', '8 Béla András')
                    if start_idx == 0:
                        if x1 > col_xs[0][1] + 2.0:
                            m = re.match(r"^(\d+)\s*(.+)$", txt)
                            if m and not m.group(2).isdigit():
                                rec.setdefault("Pos", []).append((x0, yc, col_xs[0][1], m.group(1)))
                                rec.setdefault(col_names[1], []).append((col_xs[1][0], yc, x1, m.group(2)))
                                continue
                        rec.setdefault("Pos", []).append((x0, yc, x1, txt))
                        continue

                    # University: pode transbordar texto à direita OU encostar em dígitos da próxima coluna
                    if start_idx == univ_idx:
                        if num_start_idx < n_cols and x1 > col_xs[num_start_idx][0]:
                            split_at = len(chars)
                            i = len(chars) - 1
                            while (
                                i >= 0
                                and chars[i]["c"] in "0123456789 "
                                and ((chars[i]["bbox"][0] + chars[i]["bbox"][2]) / 2.0) >= col_xs[num_start_idx][0] - 1.0
                            ):
                                split_at = i
                                i -= 1
                            univ_part = "".join(ch["c"] for ch in chars[:split_at]).strip()
                            if univ_part:
                                rec.setdefault("University", []).append((x0, yc, x1, univ_part))
                            tail_chars = chars[split_at:]
                            if tail_chars:
                                by_c: dict[int, list[dict[str, Any]]] = {}
                                for ch in tail_chars:
                                    cxc = (ch["bbox"][0] + ch["bbox"][2]) / 2.0
                                    ci = col_idx_for_x(cxc)
                                    by_c.setdefault(ci, []).append(ch)
                                for ci, chs in by_c.items():
                                    part = "".join(c["c"] for c in chs).strip()
                                    if part:
                                        rec.setdefault(col_names[ci], []).append((chs[0]["bbox"][0], yc, chs[-1]["bbox"][2], part))
                        else:
                            rec.setdefault("University", []).append((x0, yc, x1, txt))
                        continue

                    # Colunas numéricas: se um span cruzou a borda direita (ex: '142 20'), separa por char
                    if start_idx >= num_start_idx and x1 > col_xs[start_idx][1] + 1.5:
                        by_c = {}
                        for ch in chars:
                            cxc = (ch["bbox"][0] + ch["bbox"][2]) / 2.0
                            ci = col_idx_for_x(cxc)
                            by_c.setdefault(ci, []).append(ch)
                        for ci, chs in by_c.items():
                            part = "".join(c["c"] for c in chs).strip()
                            if part:
                                rec.setdefault(col_names[ci], []).append((chs[0]["bbox"][0], yc, chs[-1]["bbox"][2], part))
                        continue

                    # Colunas de texto (First name, Family name, Team)
                    rec.setdefault(col_names[start_idx], []).append((x0, yc, x1, txt))
                    if start_idx + 1 < num_start_idx and x1 > col_xs[start_idx + 1][0] + 2.0:
                        overflow_candidates.append((start_idx, x0, yc, x1, chars))

                # Divide spans de texto que fundiram 2 ou mais colunas consecutivas quando a coluna vizinha ficou vazia
                for start_idx, x0, yc, x1, chars in overflow_candidates:
                    cur_idx = start_idx
                    cur_chars = chars
                    orig_txt = "".join(ch["c"] for ch in chars).strip()
                    did_split = False
                    pieces: list[tuple[int, str]] = []
                    while cur_idx + 1 < num_start_idx and not rec.get(col_names[cur_idx + 1]):
                        if not cur_chars or cur_chars[-1]["bbox"][2] <= col_xs[cur_idx + 1][0] + 2.0:
                            break
                        left_c, right_c = _split_chars_at_boundary(cur_chars, col_xs[cur_idx + 1][0])
                        left_s = "".join(ch["c"] for ch in left_c).strip()
                        right_s = "".join(ch["c"] for ch in right_c).strip()
                        if not right_s:
                            break
                        did_split = True
                        pieces.append((cur_idx, left_s))
                        cur_idx += 1
                        cur_chars = right_c
                    if did_split:
                        pieces.append((cur_idx, "".join(ch["c"] for ch in cur_chars).strip()))
                        # Remove o span original de start_idx e insere as partes separadas
                        rec[col_names[start_idx]] = [
                            sp for sp in rec.get(col_names[start_idx], []) if sp[3] != orig_txt
                        ]
                        for pi, ps in pieces:
                            if ps:
                                rec.setdefault(col_names[pi], []).append((col_xs[pi][0], yc, col_xs[pi][1], ps))

                pos = _join_col_spans(rec.get("Pos", []), join_hyphen=False)
                if not pos or not re.fullmatch(r"\d+", pos):
                    continue
                joined = {k: _join_col_spans(v, join_hyphen=join_hyphen) for k, v in rec.items()}
                rows.append(make_row(year, **joined))
    return rows


# ---------------------------------------------------------------------------
# 2003 - 2008: PDFs tabulares horizontais
# ---------------------------------------------------------------------------
def parse_2003() -> list[dict[str, Any]]:
    cols = [
        "Pos", "First name", "Family name", "University",
        "D1_P1", "D1_P2", "D1_P3", "D1_P4", "D1_P5", "D1_P6", "Day1",
        "D2_P1", "D2_P2", "D2_P3", "D2_P4", "D2_P5", "D2_P6", "Day2",
        "Sum", "Prize_raw",
    ]
    return extract_pdf_table_unclipped(PDF_DIR / "IMC_2003_Results.pdf", 2003, cols)


def parse_2004_2008(year: int) -> list[dict[str, Any]]:
    cols = [
        "Pos", "First name", "Family name", "University",
        "Code_D1", "D1_P1", "D1_P2", "D1_P3", "D1_P4", "D1_P5", "D1_P6", "Day1",
        "Code_D2", "D2_P1", "D2_P2", "D2_P3", "D2_P4", "D2_P5", "D2_P6", "Day2",
        "Sum", "Prize_raw",
    ]
    offset = 1 if year == 2005 else 0
    return extract_pdf_table_unclipped(PDF_DIR / f"IMC_{year}_Results.pdf", year, cols, col_offset=offset)


# ---------------------------------------------------------------------------
# 2009: PDF rotacionado 90° com spans não-clippados PyMuPDF + fix de glifos
# ---------------------------------------------------------------------------
GLYPH_MAP_2009 = {
    "\x01": "ă",
    "\x02": "ě",
    "\x03": "ć",
    "\x04": "ș",
    "\x05": "ă",
    "\x06": "ł",
    "\x07": "ő",
    "\x08": "ù",
    "\x09": "č",
    "\x8a": "Š",
    "\x8e": "Ž",
    "\x96": "–",
    "\x9a": "š",
    "\x9e": "ž",
}


def fix_2009_text(s: str) -> str:
    for k, v in GLYPH_MAP_2009.items():
        s = s.replace(k, v)
    # Remove espaços indevidos criados em volta de acento que veio como span separado (ex: "B ă nic ă" -> manter juntando sem espaço!)
    return s


def parse_2009() -> list[dict[str, Any]]:
    # Em 2009 (rot=90): linha = centro (x0+x1)/2, coluna = y1 (visual left, decrescente)
    col_ranges = [
        ("Pos", 781.35, 999.0),
        ("First name", 706.0, 781.35),
        ("Family name", 611.0, 706.0),
        ("University", 435.0, 611.0),
        ("Code_D1", 411.0, 435.0),
        ("D1_P1", 390.0, 411.0),
        ("D1_P2", 370.0, 390.0),
        ("D1_P3", 351.0, 370.0),
        ("D1_P4", 332.0, 351.0),
        ("D1_P5", 313.0, 332.0),
        ("Day1", 292.0, 313.0),
        ("Code_D2", 268.0, 292.0),
        ("D2_P1", 250.0, 268.0),
        ("D2_P2", 230.0, 250.0),
        ("D2_P3", 211.0, 230.0),
        ("D2_P4", 191.0, 211.0),
        ("D2_P5", 172.0, 191.0),
        ("Day2", 147.0, 172.0),
        ("Sum", 120.0, 147.0),
        ("Prize_raw", 0.0, 120.0),
    ]

    def assign_col(y1: float) -> str:
        for name, lo, hi in col_ranges:
            if lo <= y1 < hi:
                return name
        return "Prize_raw"

    flags = pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_CLIP
    rows: list[dict[str, Any]] = []
    doc = pymupdf.open(PDF_DIR / "IMC_2009_Results.pdf")
    for page in doc:
        spans: list[tuple[float, float, float, str]] = []
        for b in page.get_text("dict", flags=flags)["blocks"]:
            for l in b.get("lines", []):
                for s in l["spans"]:
                    txt = s["text"]
                    if not txt.strip():
                        continue
                    x0, y0, x1, y1 = s["bbox"]
                    # Usar x_bot (x1) como âncora da linha (alinhamento pela base do texto: ~97.1 vs ~96.1 -> diff 1pt!)
                    spans.append((x1, y1, y0, txt))
        spans.sort(key=lambda item: (item[0], -item[1]))
        grouped: list[tuple[float, list[tuple[float, float, float, str]]]] = []
        for sp in spans:
            if not grouped or abs(sp[0] - grouped[-1][0]) > 4.5:
                grouped.append((sp[0], [sp]))
            else:
                grouped[-1][1].append(sp)

        for _, lspans in grouped:
            rec: dict[str, list[tuple[float, float, str]]] = {}
            for _, y1, y0, txt in sorted(lspans, key=lambda s: -s[1]):
                col = assign_col(y1)
                rec.setdefault(col, []).append((y1, y0, txt))
            joined: dict[str, str] = {}
            for col, parts in rec.items():
                # Concatenar spans da mesma coluna respeitando proximidade visual (y0 do anterior vs y1 do próximo)
                parts.sort(key=lambda p: -p[0])
                out = ""
                prev_y0 = None
                for y1, y0, txt in parts:
                    t = fix_2009_text(txt)
                    if prev_y0 is not None and (prev_y0 - y1) > 1.8 and not out.endswith(" ") and not t.startswith(" "):
                        out += " "
                    out += t
                    prev_y0 = y0
                joined[col] = clean_text(out)
            pos = joined.get("Pos", "")
            # Às vezes Pos e First name vêm no mesmo span ('86 Micha\x06')
            m = re.match(r"^(\d+)\s+(.+)$", pos)
            if m:
                joined["Pos"] = m.group(1)
                joined["First name"] = (m.group(2) + " " + joined.get("First name", "")).strip()
                pos = joined["Pos"]
            if not pos or not re.fullmatch(r"\d+", pos):
                continue
            rows.append(make_row(2009, **joined))
    return rows


# ---------------------------------------------------------------------------
# 2010: PDF com spans não-clippados PyMuPDF (rot=0, sem overflow de University)
# ---------------------------------------------------------------------------
def parse_2010() -> list[dict[str, Any]]:
    col_bounds = [
        ("Pos", 0.0, 49.0),
        ("First name", 49.0, 138.0),
        ("Family name", 138.0, 246.0),
        ("University", 246.0, 405.0),
        ("Code_D1", 405.0, 428.0),
        ("D1_P1", 428.0, 446.5),
        ("D1_P2", 446.5, 465.0),
        ("D1_P3", 465.0, 484.0),
        ("D1_P4", 484.0, 502.0),
        ("D1_P5", 502.0, 520.0),
        ("Day1", 520.0, 541.0),
        ("Code_D2", 541.0, 563.0),
        ("D2_P1", 563.0, 582.0),
        ("D2_P2", 582.0, 600.5),
        ("D2_P3", 600.5, 619.0),
        ("D2_P4", 619.0, 637.5),
        ("D2_P5", 637.5, 656.5),
        ("Day2", 656.5, 680.0),
        ("Sum", 680.0, 708.0),
        ("Prize_raw", 708.0, 999.0),
    ]

    def assign_col(x0: float) -> str:
        for name, lo, hi in col_bounds:
            if lo <= x0 < hi:
                return name
        return "Prize_raw"

    flags = pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_CLIP
    rows: list[dict[str, Any]] = []
    doc = pymupdf.open(PDF_DIR / "IMC_2010_Results.pdf")
    for page in doc:
        spans = []
        for b in page.get_text("dict", flags=flags)["blocks"]:
            for l in b.get("lines", []):
                for s in l["spans"]:
                    txt = s["text"].strip()
                    if not txt:
                        continue
                    spans.append((s["bbox"][0], s["bbox"][1], txt))
        spans.sort(key=lambda item: (item[1], item[0]))
        grouped: list[tuple[float, list[tuple[float, float, str]]]] = []
        for sp in spans:
            if not grouped or abs(sp[1] - grouped[-1][0]) > 4.5:
                grouped.append((sp[1], [sp]))
            else:
                grouped[-1][1].append(sp)
        for _, lspans in grouped:
            rec: dict[str, list[str]] = {}
            for x0, _, txt in sorted(lspans, key=lambda s: s[0]):
                col = assign_col(x0)
                rec.setdefault(col, []).append(txt)
            pos = " ".join(rec.get("Pos", [])).strip()
            if not pos or not re.fullmatch(r"\d+", pos):
                continue
            joined = {k: " ".join(v).strip() for k, v in rec.items()}
            rows.append(make_row(2010, **joined))
    return rows


# ---------------------------------------------------------------------------
# 2011: PDF de 6 colunas via spans não-clippados PyMuPDF (evita overflow!)
# ---------------------------------------------------------------------------
def parse_2011() -> list[dict[str, Any]]:
    col_bounds = [
        ("Pos", 0.0, 104.0),
        ("First name", 104.0, 237.0),
        ("Family name", 237.0, 391.0),
        ("University", 391.0, 588.0),
        ("Sum", 588.0, 609.5),
        ("Prize_raw", 609.5, 999.0),
    ]

    def assign_col(x0: float) -> str:
        for name, lo, hi in col_bounds:
            if lo <= x0 < hi:
                return name
        return "Prize_raw"

    flags = pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_CLIP
    rows: list[dict[str, Any]] = []
    doc = pymupdf.open(PDF_DIR / "IMC_2011_Results.pdf")
    for page in doc:
        spans = []
        for b in page.get_text("dict", flags=flags)["blocks"]:
            for l in b.get("lines", []):
                for s in l["spans"]:
                    txt = s["text"].strip()
                    if not txt:
                        continue
                    spans.append((s["bbox"][0], s["bbox"][1], txt))
        spans.sort(key=lambda item: (item[1], item[0]))
        grouped: list[tuple[float, list[tuple[float, float, str]]]] = []
        for sp in spans:
            if not grouped or abs(sp[1] - grouped[-1][0]) > 4.5:
                grouped.append((sp[1], [sp]))
            else:
                grouped[-1][1].append(sp)
        for _, lspans in grouped:
            rec: dict[str, list[str]] = {}
            for x0, _, txt in sorted(lspans, key=lambda s: s[0]):
                col = assign_col(x0)
                rec.setdefault(col, []).append(txt)
            pos = " ".join(rec.get("Pos", [])).strip()
            if not pos or not re.fullmatch(r"\d+", pos):
                continue
            joined = {k: " ".join(v).strip() for k, v in rec.items()}
            rows.append(make_row(2011, **joined))
    return rows


def parse_2013() -> list[dict[str, Any]]:
    cols = ["Pos", "First name", "Family name", "University", "Team", "Prize_raw"]
    return extract_pdf_table_unclipped(PDF_DIR / "IMC_2013_Results.pdf", 2013, cols)


# ---------------------------------------------------------------------------
# 2012: PDF rotacionado 90° com spans não-clippados (PyMuPDF flags)
# ---------------------------------------------------------------------------
def parse_2012() -> list[dict[str, Any]]:
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

    flags = pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_CLIP
    rows: list[dict[str, Any]] = []
    doc = pymupdf.open(PDF_DIR / "IMC_2012_Results.pdf")
    for page in doc:
        spans = []
        for b in page.get_text("dict", flags=flags)["blocks"]:
            for l in b.get("lines", []):
                for s in l["spans"]:
                    txt = s["text"].strip()
                    if not txt:
                        continue
                    spans.append((s["bbox"][0], s["bbox"][3], s["bbox"][1], txt))
        spans.sort(key=lambda item: (item[0], -item[1]))
        grouped: list[tuple[float, list[tuple[float, float, float, str]]]] = []
        for sp in spans:
            if not grouped or abs(sp[0] - grouped[-1][0]) > 4.5:
                grouped.append((sp[0], [sp]))
            else:
                grouped[-1][1].append(sp)

        for rx, lspans in grouped:
            rec: dict[str, list[str]] = {}
            for _, y1, y0, txt in sorted(lspans, key=lambda s: -s[1]):
                col = assign_col(y1)
                rec.setdefault(col, []).append(txt)
            pos = " ".join(rec.get("Pos", [])).strip()
            if not pos or not re.fullmatch(r"\d+", pos):
                continue
            joined = {k: " ".join(v).strip() for k, v in rec.items()}
            # Caso especial (linha 136): Family name encostou em University no mesmo span
            if not joined.get("University"):
                fam_chars, univ_chars = [], []
                for b in page.get_text("rawdict", flags=flags)["blocks"]:
                    for l in b.get("lines", []):
                        for s in l["spans"]:
                            if abs(s["bbox"][0] - rx) <= 4.5 and 552.0 <= s["bbox"][3] < 649.0:
                                for ch in s.get("chars", []):
                                    if ch["bbox"][3] >= 551.0:
                                        fam_chars.append(ch["c"])
                                    else:
                                        univ_chars.append(ch["c"])
                if univ_chars:
                    joined["Family name"] = "".join(fam_chars).strip()
                    joined["University"] = "".join(univ_chars).strip()
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
# 2026: PDF geométrico usando hlines + vlines por faixa (100% adaptável por bloco)
# ---------------------------------------------------------------------------
def parse_2026() -> list[dict[str, Any]]:
    col_names = [
        "Pos", "First name", "Family name", "University", "City",
        "D1_P1", "D1_P2", "D1_P3", "D1_P4", "D1_P5", "Day1",
        "D2_P1", "D2_P2", "D2_P3", "D2_P4", "D2_P5", "Day2",
        "Sum", "Prize_raw",
    ]

    def join_cell_words(wlist: list[dict[str, Any]], col: str) -> str:
        if not wlist:
            return ""
        wlist = sorted(wlist, key=lambda w: (w["top"], w["x0"]))
        lines: list[list[dict[str, Any]]] = []
        for w in wlist:
            if not lines or abs(w["top"] - lines[-1][0]["top"]) > 4.0:
                lines.append([w])
            else:
                lines[-1].append(w)
        line_strs = [" ".join(w["text"] for w in sorted(ln, key=lambda w: w["x0"])) for ln in lines]
        if col == "Pos":
            return clean_text("".join(line_strs))
        return clean_text("\n".join(line_strs), join_hyphen=True)

    rows: list[dict[str, Any]] = []
    with pdfplumber.open(PDF_DIR / "IMC_2026_Results.pdf") as pdf:
        for page in pdf.pages:
            hlines = sorted(
                set(
                    round(r["top"], 1)
                    for r in page.rects
                    if r["height"] <= 1.5 and r["width"] > 50 and r.get("non_stroking_color") == 0.0
                )
            )
            dedup_h: list[float] = []
            for y in hlines:
                if not dedup_h or y - dedup_h[-1] > 4.0:
                    dedup_h.append(y)

            v_rects = [
                r for r in page.rects
                if r["width"] <= 1.5 and r["height"] > 8 and r.get("non_stroking_color") == 0.0
            ]
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)

            for y_top, y_bot in zip(dedup_h[:-1], dedup_h[1:]):
                band_h = y_bot - y_top
                # Coleta as bordas verticais pretas desta faixa específica
                vs = sorted(
                    set(
                        round(r["x0"], 1)
                        for r in v_rects
                        if r["top"] <= y_top + 4.0 and r["bottom"] >= y_bot - 4.0
                        or (r["height"] >= band_h * 0.4 and r["top"] >= y_top - 3.0 and r["bottom"] <= y_bot + 3.0)
                    )
                )
                dedup_v: list[float] = []
                for x in vs:
                    if not dedup_v or x - dedup_v[-1] > 4.0:
                        dedup_v.append(x)
                if len(dedup_v) != 20:
                    continue

                band_words = [
                    w for w in words
                    if y_top <= ((w["top"] + w["bottom"]) / 2.0) <= y_bot
                ]
                if not band_words:
                    continue
                by_col: dict[str, list[dict[str, Any]]] = {}
                for w in band_words:
                    xc = (w["x0"] + w["x1"]) / 2.0
                    for idx in range(19):
                        if dedup_v[idx] - 1.5 <= xc < dedup_v[idx + 1] + 1.5:
                            by_col.setdefault(col_names[idx], []).append(w)
                            break
                pos = join_cell_words(by_col.get("Pos", []), "Pos")
                if not pos or pos.lower() == "pos" or not re.match(r"^\d", pos):
                    continue
                rec = {col: join_cell_words(wlist, col) for col, wlist in by_col.items()}
                # Ignora linha fantasma do PDF de 2026 (pág. 15) que só tem Pos '204–214.' sem nenhum outro dado
                if not any(rec.get(k) for k in ("First name", "Family name", "University", "Sum", "Prize_raw")):
                    continue
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
    if 2004 <= year <= 2008:
        return parse_2004_2008(year)
    if year == 2009:
        return parse_2009()
    if year == 2010:
        return parse_2010()
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
    BY_YEAR_DIR.mkdir(parents=True, exist_ok=True)
    all_dfs: list[pd.DataFrame] = []
    for year in range(1994, 2027):
        rows = parse_year(year)
        df = pd.DataFrame(rows, columns=STANDARD_COLUMNS)
        out_path = BY_YEAR_DIR / f"imc_results_{year}.csv"
        df.to_csv(out_path, index=False, encoding="utf-8")
        print(f"{year}: {len(df):4d} participantes -> {out_path.relative_to(ROOT_DIR)}", flush=True)
        all_dfs.append(df)

    all_df = pd.concat(all_dfs, ignore_index=True)
    all_path = OUTPUT_DIR / "imc_results_all_years.csv"
    all_df.to_csv(all_path, index=False, encoding="utf-8")
    print(f"\nConsolidado salvo: {all_path.relative_to(ROOT_DIR)} ({len(all_df):,} linhas no total)")


if __name__ == "__main__":
    main()
