"""Lê e extrai a lista padronizada de concluintes do IME (2000-2021+) a partir dos HTMLs locais.

Entrada:
- data/ime/raw/html/ime_concluintes_{periodo}.html (baixados por download_concluintes.py)

Saída:
- data/ime/processed/ime_concluintes.csv
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
RAW_HTML_DIR = ROOT_DIR / "data" / "ime" / "raw" / "html"
PROCESSED_DIR = ROOT_DIR / "data" / "ime" / "processed"
OUT_CSV = PROCESSED_DIR / "ime_concluintes.csv"

SOURCE_META: list[tuple[str, str, str]] = [
    ("2000-2004", "ime_concluintes_2000-2004.html", "https://www.ime.eb.mil.br/institucional/concluintes/2000-2004"),
    ("2005-2009", "ime_concluintes_2005-2009.html", "https://www.ime.eb.mil.br/institucional/concluintes/concluintes-de-2005-a-2009"),
    ("2010-2015", "ime_concluintes_2010-2015.html", "https://www.ime.eb.mil.br/institucional/concluintes/concluintes-de-2010-a-2015"),
    ("2016-2020", "ime_concluintes_2016-2020.html", "https://www.ime.eb.mil.br/institucional/concluintes/2016-a-2020"),
    ("2021-em-diante", "ime_concluintes_2021-em-diante.html", "https://www.ime.eb.mil.br/institucional/concluintes/2021-em-diante"),
]

# Postos/graduações encontrados nas listas oficiais de 2000-2020
# Inclui variações/typos das páginas oficiais (ex.: "1TEN", "21º TEN R/2", "Pr.Esp", "Asp/R2", "/Peru", "(AER)").
RANK_RE = re.compile(
    r"^("
    r"(?:1[º°o]?|2[º°o]?|21[º°o])\s*TEN(?:ENTE)?(?:\s*R/2)?|"
    r"ASP\.?\s*(?:OF\.?\s*)?(?:/\s*R/?2|R/?2)?|"
    r"PR\.?\s*ESP\.?|"
    r"CAP(?:IT[AÃ]O)?|"
    r"MAJ(?:OR)?|"
    r"TEN\s*CEL|TC|CEL|"
    r"SUBTEN|SGT|CIV(?:IL)?|ENG\.?"
    r")"
    r"(?:\s*(?:\([^)]+\)|/(?:Peru|El\s+Salvador|Paraguai[oa]?|Bol[ií]via|Equador|Argentina|Chile|Uruguai|Col[oô]mbia)))?"
    r"\s*[-–]?\s*(.*)$",
    re.I,
)

# Linhas sem hífen separando nome e especialidade (casos raros em 2004 e 2009)
NO_DASH_SPEC_RE = re.compile(
    r"\s+(Mec\s*/\s*Armt|Mec\s*/\s*Auto|Fort\s*/\s*Cnst|ELO|COMP|QUI|COM|CART|ELE|AUTO|FC|MAT|META|ARMT)$",
    re.I,
)


def clean_text(s: str) -> str:
    s = s.replace("\xa0", " ").replace("\u200b", "").replace("\xad", "")
    s = re.sub(r"\s+", " ", s).strip()
    return unicodedata.normalize("NFC", s)


def norm_key(s: str) -> str:
    s = unicodedata.normalize("NFKD", clean_text(s)).encode("ascii", "ignore").decode("ascii").lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def parse_student_line(raw_line: str) -> tuple[str, str, str]:
    """Retorna (rank, full_name, specialty) a partir de uma linha numerada de concluinte."""
    m_num = re.match(r"^\d+\s*[.\-)]?\s*(.*)$", raw_line)
    rest = m_num.group(1).strip() if m_num else raw_line

    # Corrige duplicação literal na mesma linha (observada no item 1 de 2017 e 2018 no HTML oficial)
    if len(rest) % 2 == 0 and rest[: len(rest) // 2] == rest[len(rest) // 2 :]:
        rest = rest[: len(rest) // 2].strip()

    m_r = RANK_RE.match(rest)
    if m_r:
        rank = clean_text(m_r.group(1))
        body_part = clean_text(m_r.group(2))
    else:
        rank = ""
        body_part = rest

    if "-" in body_part or "–" in body_part:
        idx = max(body_part.rfind("-"), body_part.rfind("–"))
        name = clean_text(body_part[:idx])
        specialty = clean_text(body_part[idx + 1 :])
    else:
        m_nd = NO_DASH_SPEC_RE.search(body_part)
        if m_nd:
            name = clean_text(body_part[: m_nd.start()])
            specialty = clean_text(m_nd.group(1))
        else:
            name = body_part
            specialty = ""

    # Remove anotações finais de letra entre parênteses (ex.: "(A)" em 2017)
    name = re.sub(r"\s*\([A-Z]\)\s*$", "", name).strip()
    return rank, name, specialty


def extract_page(period: str, filename: str, url: str) -> list[dict[str, object]]:
    path = RAW_HTML_DIR / filename
    if not path.exists():
        raise FileNotFoundError(
            f"HTML não encontrado: {path}. Execute scripts/ime/download_concluintes.py primeiro."
        )

    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "lxml")
    body = soup.find("div", attrs={"itemprop": "articleBody"}) or soup.find(
        "div", class_=re.compile("item-page", re.I)
    )
    if body is None:
        raise RuntimeError(f"Não foi possível localizar o conteúdo principal em {path}")

    for br in body.find_all("br"):
        br.replace_with("\n")

    rows: list[dict[str, object]] = []
    year: int | None = None
    turma = ""
    subsection = ""
    seq = 0

    for block in body.find_all(["p", "h1", "h2", "h3", "h4", "li"]):
        for raw in block.get_text().splitlines():
            line = clean_text(raw)
            if not line:
                continue

            m_yr = re.match(r"^CONCLUINTES\s+DE\s+(\d{4})\b", line, re.I)
            if m_yr:
                year = int(m_yr.group(1))
                turma = ""
                subsection = ""
                seq = 0
                continue

            if re.match(r"^Turma\b", line, re.I):
                turma = line
                continue

            if re.match(r"^Curso de Forma", line, re.I):
                subsection = line
                continue

            if re.match(r"^(Concluintes de|2016 a 2020|2021 em diante|Published:)", line, re.I):
                continue

            if year is None:
                continue

            seq += 1
            rank, name, specialty = parse_student_line(line)
            rows.append(
                {
                    "Year": year,
                    "Seq_in_year": seq,
                    "Turma": turma,
                    "Subsection": subsection,
                    "Rank": rank,
                    "Full_name": name,
                    "Name_norm": norm_key(name),
                    "Specialty": specialty,
                    "Source_period": period,
                    "Source_file": filename,
                    "Source_url": url,
                    "Raw_line": line,
                }
            )

    return rows


def remove_2004_duplicate_of_2005(rows: list[dict[str, object]]) -> tuple[list[dict[str, object]], int]:
    """Remove o bloco duplicado da turma de 2005 publicado ao final da lista de 2004 no site do IME.

    Na página oficial 2000-2004, os itens 93..176 de 2004 (84 nomes) repetem exatamente os
    itens 1..84 da turma de 2005 (em ordem alfabética reiniciada a partir de 'ADRIANA GUEDES...').
    """
    names_2005 = {r["Name_norm"] for r in rows if r["Year"] == 2005}
    rows_2004 = [r for r in rows if r["Year"] == 2004]
    tail_2004 = [r for r in rows_2004 if int(r["Seq_in_year"]) >= 93]

    # Só remove se a sobreposição com 2005 for esmagadora (>= 90% dos itens da cauda)
    if tail_2004 and names_2005:
        overlap = sum(1 for r in tail_2004 if r["Name_norm"] in names_2005)
        if overlap / len(tail_2004) >= 0.90:
            cleaned = [r for r in rows if not (r["Year"] == 2004 and int(r["Seq_in_year"]) >= 93)]
            return cleaned, len(tail_2004)
    return rows, 0


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    all_rows: list[dict[str, object]] = []
    for period, filename, url in SOURCE_META:
        all_rows.extend(extract_page(period, filename, url))

    cleaned_rows, dup_removed = remove_2004_duplicate_of_2005(all_rows)
    df = pd.DataFrame(cleaned_rows)

    # Validações básicas de integridade
    empty_names = df[df["Full_name"].str.strip() == ""]
    empty_ranks = df[df["Rank"].str.strip() == ""]
    empty_specs = df[df["Specialty"].str.strip() == ""]
    if len(empty_names) > 0:
        raise RuntimeError(f"ERRO: {len(empty_names)} linhas com Full_name vazio!")
    if len(empty_ranks) > 0:
        raise RuntimeError(f"ERRO: {len(empty_ranks)} linhas sem Rank reconhecido!\n{empty_ranks[['Year', 'Raw_line']]}")
    if len(empty_specs) > 0:
        raise RuntimeError(f"ERRO: {len(empty_specs)} linhas sem Specialty!\n{empty_specs[['Year', 'Raw_line']]}")

    df.to_csv(OUT_CSV, index=False, encoding="utf-8")

    by_year = sorted(Counter(df["Year"]).items())
    print(f"=== PARSE CONCLUINTES IME ({by_year[0][0]}-{by_year[-1][0]}) CONCLUÍDO ===")
    print(f"Linhas brutas extraídas:                {len(all_rows):,}")
    print(f"Duplicatas 2005 anexadas em 2004:       {dup_removed:,} (removidas)")
    print(f"Concluintes válidos salvos:             {len(df):,} ({df['Name_norm'].nunique():,} nomes únicos)")
    print(f"Anos cobertos ({len(by_year)}):                   {by_year[0][0]}-{by_year[-1][0]}")
    print("Contagem por ano:")
    print("  " + ", ".join(f"{yr}: {cnt}" for yr, cnt in by_year))
    print(f"Arquivo gerado: {OUT_CSV.relative_to(ROOT_DIR)}")


if __name__ == "__main__":
    main()
