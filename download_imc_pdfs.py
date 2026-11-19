"""Baixa os PDFs oficiais de resultados da IMC (1994-2026) do site reestruturado.

Salva em files/imc/pdf/IMC_{year}_Results.pdf (pulando arquivos já baixados).
"""

from pathlib import Path
import time
import requests

PDF_DIR = Path("files/imc/pdf")

# No site reestruturado, quase todos os anos seguem /archive/results/{year}/IMC_{year}_Results.pdf
SPECIAL_PATHS = {
    2022: "/archive/results/2022/IMC_2022_Individual_Results_all_students.pdf",
}


def get_pdf_url(year: int) -> str:
    path = SPECIAL_PATHS.get(year, f"/archive/results/{year}/IMC_{year}_Results.pdf")
    return f"https://www.imc-math.org.uk{path}"


def download_all(start_year: int = 1994, end_year: int = 2026, force: bool = False) -> None:
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    for year in range(start_year, end_year + 1):
        dest = PDF_DIR / f"IMC_{year}_Results.pdf"
        if dest.exists() and dest.stat().st_size > 1000 and not force:
            print(f"{year}: já existe ({dest.stat().st_size:,} B), pulando.")
            continue

        url = get_pdf_url(year)
        print(f"{year}: baixando {url} ...", end=" ", flush=True)
        resp = session.get(url, timeout=30)
        if resp.status_code == 200 and resp.content.startswith(b"%PDF"):
            dest.write_bytes(resp.content)
            print(f"OK ({len(resp.content):,} B)")
        else:
            print(f"FALHA (status={resp.status_code}, size={len(resp.content)})")
        time.sleep(0.3)


if __name__ == "__main__":
    download_all()
