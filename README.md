# IMC Results Pipeline (1994–2026)

Pipeline completo e reproduzível para coletar, padronizar, validar e analisar os resultados de todas as edições da **International Mathematics Competition for University Students (IMC)** de **1994 a 2026** (33 edições, 9.341 participantes), com extração e normalização dedicada de participantes e instituições brasileiras.

## Estrutura do repositório

```text
.
├── README.md
├── requirements.txt
├── run_pipeline.py                  # Executa o pipeline inteiro de ponta a ponta
├── scripts/
│   ├── download_imc_pdfs.py         # Baixa os 33 PDFs oficiais de imc-math.org.uk
│   ├── build_imc_csvs.py            # Extrai e padroniza os 33 anos para o mesmo esquema CSV
│   ├── validate_imc_csvs.py         # Validação aritmética, posicional e textual ano a ano
│   └── filter_brazil.py             # Filtra e normaliza universidades e estudantes brasileiros
└── data/
    ├── raw/
    │   ├── html/                    # HTMLs salvos do site antigo (usados em 1998–2002 e 2015–2019)
    │   ├── csv_raw/                 # CSVs extraídos do site antigo (usados em 2020–2025)
    │   └── pdf/                     # PDFs oficiais do site reestruturado (1994–2026, ignorado no git)
    └── processed/
        ├── by_year/                 # Um CSV padronizado por ano (imc_results_1994.csv .. 2026.csv)
        ├── imc_results_all_years.csv
        └── brazil/
            ├── imc_brazil_only_br_universities.csv  # Participações representando instituições do Brasil
            ├── imc_brazil_participations.csv        # Instituições do Brasil + brasileiros no exterior
            ├── imc_brazil_people.csv                # 1 linha por estudante único (nomes normalizados)
            ├── imc_brazil_universities.csv          # Resumo por instituição brasileira canônica
            └── imc_brazil_by_year.csv               # Série histórica anual (2003–2026)
```

## Como executar

1. Crie/ative o ambiente virtual e instale as dependências:
   ```bash
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```
   *(Requer `pdftotext` do pacote `poppler-utils` para os PDFs de 1994–1997.)*

2. Rode o pipeline completo:
   ```bash
   # Usando os arquivos em cache local (data/raw/):
   .venv/bin/python run_pipeline.py

   # Para baixar PDFs faltantes antes de processar:
   .venv/bin/python run_pipeline.py --download
   ```

Ou execute etapas individuais em `scripts/`:
```bash
.venv/bin/python scripts/download_imc_pdfs.py
.venv/bin/python scripts/build_imc_csvs.py
.venv/bin/python scripts/validate_imc_csvs.py
.venv/bin/python scripts/filter_brazil.py
```

## Esquema dos CSVs gerados (`data/processed/`)

Todos os 33 arquivos em `data/processed/by_year/` e `imc_results_all_years.csv` compartilham as mesmas 28 colunas:

`Year`, `Pos`, `First name`, `Family name`, `Full name`, `University`, `Team`, `City`, `Country`, `Code_D1`, `D1_P1`..`D1_P6`, `Day1`, `Code_D2`, `D2_P1`..`D2_P6`, `Day2`, `Sum`, `Prize`, `Prize_raw`.

Nos arquivos em `data/processed/brazil/`, são adicionadas as colunas de normalização:
`Person_id`, `Person_canonical`, `University_canonical`, `University_full_name`, `Is_Brazilian_University` e `Inclusion_reason`.
