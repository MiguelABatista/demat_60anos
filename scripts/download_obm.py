"""Baixa todas as páginas oficiais de premiados da OBM (1979-2025) de obm.org.br.

Salva os HTMLs em data/obm/raw/html/obm_{year}.html (mais o índice em index_premiados.html).
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT_DIR = Path(__file__).resolve().parent.parent
RAW_HTML_DIR = ROOT_DIR / "data" / "obm" / "raw" / "html"
INDEX_URL = "https://www.obm.org.br/quem-somos/premiados-da-obm/"
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}


def main() -> None:
    RAW_HTML_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update(HEADERS)

    # 1. Baixa o índice principal para descobrir todos os anos/links publicados
    idx_path = RAW_HTML_DIR / "index_premiados.html"
    r = session.get(INDEX_URL, timeout=30)
    r.raise_for_status()
    idx_path.write_text(r.text, encoding="utf-8")
    soup = BeautifulSoup(r.text, "lxml")

    year_urls: dict[int, str] = {}
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        m = re.search(r"premiados-obm-(\d{4})", href)
        if m:
            year_urls[int(m.group(1))] = href

    # Garante cobertura completa de 1979 até o ano mais recente encontrado (e testa +1 caso já publicado)
    max_yr = max(year_urls) if year_urls else 2025
    for yr in range(1979, max_yr + 1):
        year_urls.setdefault(yr, f"https://www.obm.org.br/premiados-obm-{yr}/")

    print(f"Encontrados {len(year_urls)} anos ({min(year_urls)}-{max(year_urls)}).", flush=True)

    ok, skipped, failed = 0, 0, []
    for yr in sorted(year_urls):
        out = RAW_HTML_DIR / f"obm_{yr}.html"
        if out.exists() and out.stat().st_size > 1000:
            skipped += 1
            continue
        url = year_urls[yr]
        try:
            resp = session.get(url, timeout=30)
            if resp.status_code == 200:
                out.write_text(resp.text, encoding="utf-8")
                ok += 1
                print(f"  {yr}: OK ({len(resp.text):,} bytes)", flush=True)
            else:
                failed.append((yr, resp.status_code, url))
                print(f"  {yr}: HTTP {resp.status_code} ({url})", flush=True)
        except Exception as exc:
            failed.append((yr, str(exc), url))
            print(f"  {yr}: ERRO {exc}", flush=True)
        time.sleep(0.15)

    print(f"\nConcluído: {ok} baixados, {skipped} já em cache, {len(failed)} falhas.")
    if failed:
        for item in failed:
            print("  FALHA:", item)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
