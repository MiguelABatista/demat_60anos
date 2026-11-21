"""Baixa todas as páginas e PDFs oficiais de resultados da CIIM (2009-2026) de ciim.uan.edu.co.

Salva em data/ciim/raw/{html,pdf}/ (pulando arquivos já baixados).
"""

from __future__ import annotations

import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

ROOT_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT_DIR / "data" / "ciim" / "raw"
HTML_DIR = RAW_DIR / "html"
PDF_DIR = RAW_DIR / "pdf"
IMG_DIR = RAW_DIR / "img"

BASE_URL = "https://ciim.uan.edu.co"

# Mapeamento exato das páginas/PDFs de cada edição em ciim.uan.edu.co
CIIM_SOURCES: dict[int, list[tuple[str, str]]] = {
    2009: [
        ("cuadro_de_honor", "/ciim-2009-participantes/cuadro-de-honor"),
        ("concursantes", "/ciim-2009-participantes/concursantes"),
    ],
    2010: [
        ("cuadro_de_honor", "/ciim-2010-participantes/cuadro-de-honor"),
        ("concursantes", "/ciim-2010-participantes/concursantes"),
    ],
    2011: [
        ("cuadro_de_honor", "/ciim-2011-participantes/cuadro-de-honor"),
        ("concursantes", "/ciim-2011-participantes/concursantes"),
    ],
    2012: [
        ("cuadro_de_honor", "/ciim-2012-participantes/cuadro-de-honor"),
        ("resultados", "/ciim-2012-participantes/resultados"),
        ("concursantes", "/ciim-2012-participantes/concursantes"),
    ],
    2013: [
        ("cuadro_de_honor", "/ciim-2013-participantes/ciim-2013-cuadro-de-honor"),
        ("resultados", "/ciim-2013-participantes/ciim-2013-resultados"),
        ("concursantes", "/ciim-2013-participantes/ciim-2013-concursantes"),
    ],
    2014: [
        ("cuadro_de_honor", "/ciim-2014-participantes/cuadro-de-honor"),
        ("resultados", "/ciim-2014-participantes/resultados"),
    ],
    2015: [
        ("cuadro_de_honor", "/ciim-2015-participantes/cuadro-de-honor"),
        ("concursantes", "/ciim-2015-participantes/concursantes"),
    ],
    2016: [
        ("cuadro_de_honor", "/ciim-2016-participantes/cuadro-de-honor"),
        ("concursantes", "/ciim-2016-participantes/concursantes"),
    ],
    2017: [
        ("cuadro_de_honor", "/ciim-2017-participantes/cuadro-de-honor"),
        ("resultados", "/ciim-2017-participantes/resultados"),
        ("concursantes", "/ciim-2017-participantes/concursantes"),
    ],
    2018: [
        ("cuadro_de_honor", "/ciim-2018-participantes/cuadro-de-honor"),
        ("resultados", "/ciim-2018-participantes/resultados"),
        ("concursantes", "/ciim-2018-participantes/concursantes"),
    ],
    2019: [
        ("medalleria_pdf", "/images/VersionesCIIM/2019/documentos/Participantes-Medalleria-CIIM2019.pdf"),
    ],
    2020: [
        ("medalleria_pdf", "/images/VersionesCIIM/2020/documentos/Medalleria-CIIM2020.pdf"),
        ("participantes_pdf", "/images/VersionesCIIM/2020/documentos/Participantes-CIIM2020.pdf"),
    ],
    2021: [
        ("medalleria_pdf", "/images/VersionesCIIM/2021/documentos/Medalleria.pdf"),
        ("participantes_pdf", "/images/VersionesCIIM/2021/documentos/Participantes.pdf"),
    ],
    2022: [
        ("medalleria_pdf", "/images/VersionesCIIM/2022/documentos/Medalleria.pdf"),
    ],
    2023: [
        ("resultados", "/ciim-2023-resultados"),
    ],
    2024: [
        ("resultados", "/ciim-2024-resultados"),
    ],
    2025: [
        ("resultados_pdf", "/images/VersionesCIIM/2025/documentos/Resultados.pdf"),
        ("participantes_pdf", "/images/VersionesCIIM/2025/documentos/Participantes.pdf"),
    ],
    2026: [
        ("resultados", "/ciim-2026-participantes/resultados"),
        ("delegaciones", "/ciim-2026-participantes/ciim-2026-delegaciones"),
    ],
}


def download_file(session: requests.Session, url: str, dest: Path, force: bool = False) -> bytes | None:
    if dest.exists() and dest.stat().st_size > 500 and not force:
        print(f"  já existe: {dest.name} ({dest.stat().st_size:,} B)")
        return dest.read_bytes()
    print(f"  baixando {url} ...", end=" ", flush=True)
    resp = session.get(url, timeout=30)
    if resp.status_code == 200:
        dest.write_bytes(resp.content)
        print(f"OK ({len(resp.content):,} B)")
        return resp.content
    print(f"FALHA (status={resp.status_code})")
    return None


def download_all(force: bool = False) -> None:
    HTML_DIR.mkdir(parents=True, exist_ok=True)
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    for year, items in sorted(CIIM_SOURCES.items()):
        print(f"=== CIIM {year} ===", flush=True)
        for kind, path in items:
            url = urljoin(BASE_URL, path)
            is_pdf = path.lower().endswith(".pdf")
            if is_pdf:
                dest = PDF_DIR / f"ciim_{year}_{kind}.pdf"
                download_file(session, url, dest, force=force)
            else:
                dest = HTML_DIR / f"ciim_{year}_{kind}.html"
                content = download_file(session, url, dest, force=force)
                if content:
                    soup = BeautifulSoup(content.decode("utf-8", errors="replace"), "lxml")
                    # 1. PDFs em links <a href> ou em <iframe src>
                    pdf_links: list[str] = []
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        if href.lower().endswith(".pdf") and ("VersionesCIIM" in href or str(year) in href):
                            pdf_links.append(href)
                    for iframe in soup.find_all("iframe", src=True):
                        src = iframe["src"]
                        if src.lower().endswith(".pdf") and ("VersionesCIIM" in src or str(year) in src):
                            if "BancoDeProblemas" not in src and "PruebaDia" not in src:
                                pdf_links.append(src)
                    for href in dict.fromkeys(pdf_links):
                        fname = Path(href).name
                        p_dest = PDF_DIR / f"ciim_{year}_{kind}_{fname}"
                        download_file(session, urljoin(BASE_URL, href), p_dest, force=force)
                        time.sleep(0.2)

                    # 2. Imagens de resultados / cuadro de honor / concursantes (2014, 2015, 2017)
                    img_links: list[str] = []
                    for img in soup.find_all("img", src=True):
                        src = img["src"]
                        low = src.lower()
                        if "versionesciim" in low and any(
                            k in low for k in ["cuadrohonor", "resultados", "concursantes", "medalleria"]
                        ):
                            img_links.append(src)
                    for src in dict.fromkeys(img_links):
                        fname = Path(src).name
                        i_dest = IMG_DIR / f"ciim_{year}_{kind}_{fname}"
                        download_file(session, urljoin(BASE_URL, src), i_dest, force=force)
                        time.sleep(0.2)
            time.sleep(0.2)


if __name__ == "__main__":
    download_all()
