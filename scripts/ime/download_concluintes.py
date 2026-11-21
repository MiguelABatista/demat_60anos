"""Baixa as páginas oficiais de concluintes do IME (2000 em diante) em www.ime.eb.mil.br.

Salva os HTMLs brutos em data/ime/raw/html/ (pulando arquivos já em cache,
a menos que --force seja passado).
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import requests
import urllib3

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
RAW_HTML_DIR = ROOT_DIR / "data" / "ime" / "raw" / "html"
SYSTEM_CA_BUNDLE = Path("/etc/ssl/certs/ca-certificates.crt")

IME_CONCLUINTES_SOURCES: list[tuple[str, str]] = [
    ("2000-2004", "https://www.ime.eb.mil.br/institucional/concluintes/2000-2004"),
    ("2005-2009", "https://www.ime.eb.mil.br/institucional/concluintes/concluintes-de-2005-a-2009"),
    ("2010-2015", "https://www.ime.eb.mil.br/institucional/concluintes/concluintes-de-2010-a-2015"),
    ("2016-2020", "https://www.ime.eb.mil.br/institucional/concluintes/2016-a-2020"),
    ("2021-em-diante", "https://www.ime.eb.mil.br/institucional/concluintes/2021-em-diante"),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}


def fetch_with_ssl_fallback(session: requests.Session, url: str) -> requests.Response:
    """Tenta HTTPS com verificação padrão, depois CA do sistema, depois sem verificação (cadeia .eb.mil.br)."""
    try:
        return session.get(url, timeout=30, verify=True)
    except requests.exceptions.SSLError:
        if SYSTEM_CA_BUNDLE.exists():
            try:
                return session.get(url, timeout=30, verify=str(SYSTEM_CA_BUNDLE))
            except requests.exceptions.SSLError:
                pass
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        print("(SSL cadeia incompleta, usando verify=False) ", end="", flush=True)
        return session.get(url, timeout=30, verify=False)


def download_all(force: bool = False) -> None:
    RAW_HTML_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update(HEADERS)

    ok, skipped, failed = 0, 0, []
    for period, url in IME_CONCLUINTES_SOURCES:
        dest = RAW_HTML_DIR / f"ime_concluintes_{period}.html"
        if dest.exists() and dest.stat().st_size > 1000 and not force:
            print(f"  [cache] {period}: {dest.name} ({dest.stat().st_size:,} bytes)", flush=True)
            skipped += 1
            continue

        print(f"  [GET] {period}: {url} ...", end=" ", flush=True)
        try:
            resp = fetch_with_ssl_fallback(session, url)
            if resp.status_code == 200:
                resp.encoding = resp.apparent_encoding or "utf-8"
                dest.write_text(resp.text, encoding="utf-8")
                print(f"OK ({len(resp.text):,} chars)", flush=True)
                ok += 1
            else:
                print(f"HTTP {resp.status_code}", flush=True)
                failed.append((period, resp.status_code, url))
        except Exception as exc:
            print(f"ERRO: {exc}", flush=True)
            failed.append((period, str(exc), url))
        time.sleep(0.25)

    print(f"\nDownload IME concluído: {ok} baixados, {skipped} em cache, {len(failed)} falhas.")
    if failed:
        for item in failed:
            print("  FALHA:", item)
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Baixa páginas de concluintes do IME (2000-2020).")
    parser.add_argument("--force", action="store_true", help="Rebaixa mesmo que já exista em cache.")
    args = parser.parse_args()
    download_all(force=args.force)


if __name__ == "__main__":
    main()
