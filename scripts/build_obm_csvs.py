"""Extrai e padroniza todos os premiados da OBM (1979-2025) a partir dos HTMLs oficiais.

Fontes em cache local: data/obm/raw/html/obm_{year}.html (baixadas por scripts/download_obm.py).

Saídas:
- data/obm/processed/by_year/obm_results_{year}.csv (um CSV padronizado por ano, 1979 a 2025)
- data/obm/processed/obm_results_all_years.csv      (consolidado com todos os 47 anos)
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

import pandas as pd
from bs4 import BeautifulSoup, Tag

ROOT_DIR = Path(__file__).resolve().parent.parent
RAW_HTML_DIR = ROOT_DIR / "data" / "obm" / "raw" / "html"
OUTPUT_DIR = ROOT_DIR / "data" / "obm" / "processed"
BY_YEAR_DIR = OUTPUT_DIR / "by_year"

STANDARD_COLUMNS = [
    "Year",
    "Edition",
    "Level",
    "Level_raw",
    "Rank_in_level",
    "Full name",
    "City",
    "State",
    "City_State_raw",
    "Points",
    "Prize",
    "Prize_raw",
]

VALID_UFS = {
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT",
    "PA", "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO",
}

# Cidades publicadas sem UF na tabela oficial (apenas 2 casos históricos confirmados)
CITY_WITHOUT_UF_FALLBACK = {
    "juiz de fora": ("Juiz de Fora", "MG"),
    "s j do rio preto": ("S.J. do Rio Preto", "SP"),
}


def clean_text(val: Any) -> str:
    if val is None:
        return ""
    s = str(val).replace("\xa0", " ").replace("\u200b", "").replace("\xad", "")
    # Remove eventuais restos de tags HTML malformadas no site oficial (ex.: '/B>', '/td>')
    s = re.sub(r"</?[a-zA-Z]+>|/[a-zA-Z]+>", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return unicodedata.normalize("NFC", s)


def norm_key(s: str) -> str:
    s = unicodedata.normalize("NFKD", clean_text(s)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", s.lower())).strip()


def normalize_prize(raw: str) -> str:
    s = clean_text(raw)
    if not s:
        return ""
    k = norm_key(s)
    if "ouro" in k and "especial" in k:
        return "Ouro Especial"
    if k == "ouro":
        return "Ouro"
    if k == "prata":
        return "Prata"
    if k == "bronze":
        return "Bronze"
    if "honrosa" in k or k == "m honrosa":
        return "Menção Honrosa"
    if "destaque" in k:
        return "Destaque Regional"
    if "demais premiados" in k:
        return "Premiado"
    m = re.match(r"^(\d+)\s*[ºo°]?\s*pr[eê]mio$", s.lower())
    if m:
        return f"{m.group(1)}º Prêmio"
    return s


def normalize_level(raw: str, year: int, table_idx: int, total_tables: int) -> str:
    k = norm_key(raw)
    if "universit" in k:
        return "Nível Universitário"
    if "nivel 1" in k or "primeiro nivel" in k:
        return "Nível 1"
    if "nivel 2" in k or "segundo nivel" in k:
        return "Nível 2"
    if "nivel 3" in k or "terceiro nivel" in k:
        return "Nível 3"
    if "junior" in k:
        return "Júnior"
    if "senior" in k:
        return "Sênior"
    if year <= 1990:
        return "Único"
    if total_tables == 4:
        return ["Nível 1", "Nível 2", "Nível 3", "Nível Universitário"][table_idx]
    if total_tables == 3:
        return ["Nível 1", "Nível 2", "Nível 3"][table_idx]
    if total_tables == 2:
        return ["Júnior", "Sênior"][table_idx]
    return raw or "Único"


def find_table_heading(table: Tag) -> str:
    """Encontra o título de seção imediatamente anterior à tabela (pulando tags vazias)."""
    for prev in table.find_all_previous(["h1", "h2", "h3", "h4", "h5", "p", "strong", "div"]):
        if prev.find("table") or prev.find_parent("table"):
            continue
        txt = clean_text(prev.get_text(" ", strip=True))
        if not txt:
            continue
        return txt
    return ""


def split_city_state(raw: str) -> tuple[str, str]:
    s = clean_text(raw)
    if not s or s in {"-", "–", "—"}:
        return "", ""
    # Padrão principal: "Cidade – UF", "Cidade - UF", "Cidade/UF" ou "Cidade  UF"
    m = re.search(r"(?:\s*[-–—/]\s*|\s+)([A-Za-z]{2})\s*$", s)
    if m and m.group(1).upper() in VALID_UFS:
        city = s[: m.start()].strip(" -–—/")
        uf = m.group(1).upper()
        return city, uf
    k = norm_key(s)
    if k in CITY_WITHOUT_UF_FALLBACK:
        return CITY_WITHOUT_UF_FALLBACK[k]
    return s, ""


def parse_year(year: int) -> list[dict[str, Any]]:
    path = RAW_HTML_DIR / f"obm_{year}.html"
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "lxml")
    art = soup.find("article") or soup.find("main") or soup
    tables = art.find_all("table")
    edition = year - 1978

    rows: list[dict[str, Any]] = []
    rank_counters: dict[str, int] = {}

    for ti, table in enumerate(tables):
        trs = table.find_all("tr")
        if not trs:
            continue
        heading = find_table_heading(table)
        level = normalize_level(heading, year, ti, len(tables))
        level_raw = heading

        hdr = [clean_text(c.get_text(" ", strip=True)) for c in trs[0].find_all(["th", "td"])]
        hlow = [norm_key(h) for h in hdr]

        name_idx = next((i for i, h in enumerate(hlow) if "nome" in h), 0)
        pts_idx = next((i for i, h in enumerate(hlow) if h in {"pontos", "total"}), None)
        city_idx = next((i for i, h in enumerate(hlow) if "cidade" in h), None)
        prize_idx = next((i for i, h in enumerate(hlow) if "premio" in h), None)

        default_prize_raw = "Demais Premiados" if (year == 1979 and ti == 1 and prize_idx is None) else ""

        for tr in trs[1:]:
            cells = [clean_text(c.get_text(" ", strip=True)) for c in tr.find_all(["th", "td"])]
            if not any(cells) or len(cells) != len(hdr):
                continue
            name = cells[name_idx]
            if not name or norm_key(name) == "nome":
                continue

            rank_counters[level] = rank_counters.get(level, 0) + 1
            pts = cells[pts_idx] if pts_idx is not None else ""
            city_raw = cells[city_idx] if city_idx is not None else ""
            city, state = split_city_state(city_raw)
            prize_raw = cells[prize_idx] if prize_idx is not None else default_prize_raw
            prize = normalize_prize(prize_raw)

            rows.append(
                {
                    "Year": year,
                    "Edition": edition,
                    "Level": level,
                    "Level_raw": level_raw,
                    "Rank_in_level": rank_counters[level],
                    "Full name": name,
                    "City": city,
                    "State": state,
                    "City_State_raw": city_raw,
                    "Points": pts,
                    "Prize": prize,
                    "Prize_raw": prize_raw,
                }
            )
    return rows


def main() -> None:
    BY_YEAR_DIR.mkdir(parents=True, exist_ok=True)
    all_dfs: list[pd.DataFrame] = []

    for year in range(1979, 2026):
        rows = parse_year(year)
        df = pd.DataFrame(rows, columns=STANDARD_COLUMNS)
        out_path = BY_YEAR_DIR / f"obm_results_{year}.csv"
        df.to_csv(out_path, index=False, encoding="utf-8")
        lvls = df["Level"].value_counts().to_dict()
        lvl_str = ", ".join(f"{k}:{v}" for k, v in lvls.items())
        print(f"{year} ({year - 1978:2d}ª): {len(df):3d} premiados [{lvl_str}] -> {out_path.relative_to(ROOT_DIR)}")
        all_dfs.append(df)

    all_df = pd.concat(all_dfs, ignore_index=True)
    all_path = OUTPUT_DIR / "obm_results_all_years.csv"
    all_df.to_csv(all_path, index=False, encoding="utf-8")
    print(f"\nConsolidado OBM salvo: {all_path.relative_to(ROOT_DIR)} ({len(all_df):,} linhas em 47 anos)")


if __name__ == "__main__":
    main()
