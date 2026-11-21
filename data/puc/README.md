# Cruzamento inicial: OBM universitária e PUC-Rio

`obm_university_puc_rio_candidates.csv` contém participantes do nível universitário da OBM com registros em Rio de Janeiro ou Niterói, cruzados com:

- as participações brasileiras da IMC e da CIIM (correspondência exata de nome normalizado; registros sem instituição informada e participações como equipe da OBM não contam como evidência de universidade);
- a lista isolada de premiados da OBM-U no IME (`data/ime/processed/obm_university_ime_awardees.csv`), consultada via `scripts/apply_ime_to_puc_candidates.py` (somente registros com janela temporal compatível com a graduação no IME).

Classificações:

- `PUC_RIO_SEM_CONTRADICAO`: há registro da PUC-Rio, sem registro de outra instituição nas competições cruzadas.
- `OUTRA_INSTITUICAO`: há registro de outra instituição, sem registro da PUC-Rio.
- `CONFLITO`: há registros tanto da PUC-Rio quanto de outra instituição.
- `SEM_EVIDENCIA`: não foi encontrado registro explícito de instituição no cruzamento.

As evidências podem ser de anos diferentes. Portanto, essas categorias são filtros preliminares, não confirmação do vínculo no ano da premiação da OBM. `SEM_EVIDENCIA` não significa que a pessoa não seja da PUC.
