# Processo isolado: Concluintes do IME (2000 em diante) × OBM Universitária

Esta pasta (`data/ime/`) e os scripts em `scripts/ime/` formam um processo completamente isolado do restante do repositório para:

1. **Baixar** as 5 páginas oficiais de concluintes do Instituto Militar de Engenharia (IME) em `www.ime.eb.mil.br` (`data/ime/raw/html/`):
   - 2000–2004: https://www.ime.eb.mil.br/institucional/concluintes/2000-2004
   - 2005–2009: https://www.ime.eb.mil.br/institucional/concluintes/concluintes-de-2005-a-2009
   - 2010–2015: https://www.ime.eb.mil.br/institucional/concluintes/concluintes-de-2010-a-2015
   - 2016–2020: https://www.ime.eb.mil.br/institucional/concluintes/2016-a-2020
   - 2021 em diante: https://www.ime.eb.mil.br/institucional/concluintes/2021-em-diante *(no momento, o portal do IME publicou apenas a turma de 2021 nesta página; quando o IME publicar 2022+, basta reexecutar `run_ime_pipeline.py --download --force`)*
2. **Extrair e padronizar** todos os concluintes em `data/ime/processed/ime_concluintes.csv` (removendo automaticamente o bloco duplicado de 84 nomes da turma de 2005 publicado ao final da lista de 2004 no site do IME).
3. **Montar a lista consultável de premiados da OBM-U no IME** em `data/ime/processed/obm_university_ime_awardees.csv`, cruzando `ime_concluintes.csv` com `data/obm/processed/university/obm_university_people.csv`.

## Como executar

```bash
# Usando os HTMLs já baixados em data/ime/raw/html/:
.venv/bin/python scripts/ime/run_ime_pipeline.py

# Para baixar novamente os HTMLs antes de processar:
.venv/bin/python scripts/ime/run_ime_pipeline.py --download
```

## Critérios de cruzamento (`obm_university_ime_awardees.csv`)

- `EXACT`: correspondência exata de nome normalizado (sem acentos/pontuação) contra o nome canônico ou variantes oficiais na OBM-U.
- `AUDITED_ALIAS`: 6 equivalências auditadas manualmente por variação mínima de grafia/preposição/abreviação (`César`/`Cezár`, `Taline`/`Talita`, `S.`/`Silveira`, omissão de `de`, `e`/`de`, typo `RICON`/`Rincon`).
- `Temporal_Check`: marca `COMPATIVEL_GRADUACAO` quando `0 <= (ano_formatura_IME - ano_OBM) <= 5` para todas as premiações do estudante na OBM-U.

## Consumo pelo restante do projeto

Outros módulos do repositório não precisam ler os HTMLs nem repetir o parsing do IME — basta consultar `data/ime/processed/obm_university_ime_awardees.csv` (por exemplo, via `scripts/apply_ime_to_puc_candidates.py`).
