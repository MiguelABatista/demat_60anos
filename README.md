# IMC, CIIM & OBM Results Pipelines

Pipelines completos e reproduzíveis para coletar, padronizar, validar ano a ano e analisar os resultados das competições de matemática, com normalização dedicada de nomes de pessoas, universidades e cidades:

- **IMC (International Mathematics Competition for University Students):** 1994–2026 (33 edições, 9.341 participantes, 613 participações brasileiras / 354 estudantes únicos).
- **CIIM (Competencia Iberoamericana Interuniversitaria de Matemáticas):** 2009–2026 (18 edições, 1.088 participantes, 277 participações brasileiras / 189 estudantes únicos).
- **OBM (Olimpíada Brasileira de Matemática):** 1979–2025 (47 edições, todos os níveis: 7.542 premiações; Nível Universitário 2001–2025: 1.341 premiações / 670 estudantes únicos).

## Estrutura do repositório

```text
.
├── README.md
├── requirements.txt
├── run_pipeline.py                       # Executa os pipelines IMC, CIIM e/ou OBM de ponta a ponta
├── scripts/
│   ├── download_imc_pdfs.py              # Baixa os 33 PDFs oficiais da IMC (imc-math.org.uk)
│   ├── build_imc_csvs.py                 # Extrai e padroniza os 33 anos da IMC
│   ├── validate_imc_csvs.py              # Validação aritmética, posicional e textual da IMC
│   ├── filter_brazil.py                  # Filtra e normaliza universidades e estudantes BR na IMC
│   ├── download_ciim.py                  # Baixa HTMLs, PDFs e imagens oficiais da CIIM (ciim.uan.edu.co)
│   ├── build_ciim_csvs.py                # Extrai e padroniza os 18 anos da CIIM
│   ├── validate_ciim_csvs.py             # Validação aritmética e textual da CIIM ano a ano
│   ├── filter_ciim_brazil.py             # Filtra e normaliza universidades e estudantes BR na CIIM
│   ├── download_obm.py                   # Baixa os 47 HTMLs oficiais da OBM (obm.org.br)
│   ├── build_obm_csvs.py                 # Extrai e padroniza os 47 anos da OBM (todos os níveis)
│   ├── validate_obm_csvs.py              # Validação estrutural e textual da OBM ano a ano
│   └── normalize_obm.py                  # Normaliza cidades, UFs e nomes de estudantes (OBM-U + geral)
└── data/
    ├── raw/                              # Fontes brutas da IMC (html/, csv_raw/, pdf/ ignorado no git)
    ├── processed/                        # Saídas padronizadas da IMC (by_year/, all_years, brazil/)
    ├── ciim/
    │   ├── raw/                          # Fontes brutas da CIIM (html/, transcribed/, pdf/ e img/ ignorados)
    │   └── processed/                    # Saídas padronizadas da CIIM (by_year/, all_years, brazil/)
    └── obm/
        ├── raw/html/                     # HTMLs oficiais da OBM (1979-2025)
        └── processed/
            ├── by_year/                  # obm_results_1979.csv .. obm_results_2025.csv
            ├── obm_results_all_years.csv
            ├── university/               # Nível Universitário (2001-2025) normalizado
            │   ├── obm_university_participations.csv
            │   ├── obm_university_people.csv
            │   ├── obm_university_by_state.csv
            │   └── obm_university_by_year.csv
            └── summary/                  # Resumos históricos (todos os níveis, 1979-2025)
                ├── obm_all_by_year_level.csv
                ├── obm_all_by_state.csv
                └── obm_all_by_city.csv
```

## Como executar

1. Crie/ative o ambiente virtual e instale as dependências:
   ```bash
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```
   *(Requer `pdftotext` do pacote `poppler-utils` para os PDFs de 1994–1997 da IMC.)*

2. Rode o pipeline completo (ou apenas uma competição):
   ```bash
   # IMC + CIIM + OBM usando o cache local:
   .venv/bin/python run_pipeline.py

   # Somente uma competição:
   .venv/bin/python run_pipeline.py --competition imc
   .venv/bin/python run_pipeline.py --competition ciim
   .venv/bin/python run_pipeline.py --competition obm

   # Para baixar fontes oficiais faltantes antes de processar:
   .venv/bin/python run_pipeline.py --download
   ```

## Esquemas dos CSVs gerados

### IMC (`data/processed/`)
`Year`, `Pos`, `First name`, `Family name`, `Full name`, `University`, `Team`, `City`, `Country`, `Code_D1`, `D1_P1`..`D1_P6`, `Day1`, `Code_D2`, `D2_P1`..`D2_P6`, `Day2`, `Sum`, `Prize`, `Prize_raw`.
Em `brazil/`: adiciona `Person_id`, `Person_canonical`, `University_canonical`, `University_full_name`, `Is_Brazilian_University`, `Inclusion_reason`.

### CIIM (`data/ciim/processed/`)
`Year`, `Pos`, `First name`, `Family name`, `Full name`, `University`, `Country`, `Code`, `P1`..`P6`, `Total`, `Prize`, `Prize_raw`.
Em `brazil/`: adiciona `Person_id`, `Person_canonical`, `University_canonical`, `University_full_name`, `OBM_team`.

### OBM (`data/obm/processed/`)
`Year`, `Edition`, `Level`, `Level_raw`, `Rank_in_level`, `Full name`, `City`, `State`, `City_State_raw`, `Points`, `Prize`, `Prize_raw`.
Em `university/`: adiciona `Person_id`, `Person_canonical`, `City_canonical`.
