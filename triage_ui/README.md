# Micro-interface de Triagem Manual (descartável)

Esta pasta (`triage_ui/`) é completamente separada do restante do projeto e pode ser removida a qualquer momento sem afetar o repositório.

## Como usar

1. Dê duplo clique em **`iniciar.bat`** (ou execute `triage_ui\iniciar.bat` pelo terminal).
2. A janela abre no canto da tela (**Sempre no topo**) e abre automaticamente no **Firefox** a busca no Google pelo primeiro candidato pendente entre os 95 `SEM_EVIDENCIA`.
3. Preencha os 2 passos rápidos:
   - **1. Faculdade / Instituição:** digite (ex.: `PUC-Rio`, `UFRJ`, `IME`, `FGV`, `UFF`) ou clique nos botões rápidos.
     - Se contiver `PUC` → classifica automaticamente como `CONFIRMADO_PUC`.
     - Qualquer outra instituição → classifica automaticamente como `OUTRA_INSTITUICAO`.
     - `Sem evidência` → marca `SEM_EVIDENCIA` (não exige URL).
   - **2. URL da fonte:** copie o link no Firefox (`Ctrl+L`, `Ctrl+C`) e cole com **`Ctrl+V`** ou **`F4`** (botão `Colar (F4)`).
     - O tipo de fonte (`Lattes`, `PUC-Rio`, `Escavador`, `LinkedIn`, `OBM`, `IMPA`, `Site_IES`, `Outro`) é detectado automaticamente pela URL e salvo na coluna `Source_Type`.
     - A opção **`Exigir fonte`** vem marcada para você não salvar uma faculdade sem o link por engano (pode desmarcar se precisar).
4. Pressione **`Enter`** para salvar e avançar para o próximo candidato (já abrindo o Firefox automaticamente).
5. Todo salvamento grava imediatamente em:
   `data/puc/obm_university_sem_evidencia_manual_triage.csv`
   (sem alterar `data/puc/obm_university_puc_rio_candidates.csv`).
6. Você pode fechar a qualquer momento e retomar depois exatamente de onde parou.

## Atalhos
- **`Enter`**: Avança para o campo URL (se faltar fonte) ou Salva e vai para o próximo
- **`F2`**: Abrir busca no Google no Firefox (`"Nome Completo"`)
- **`F3`**: Abrir busca `"Nome Completo" "PUC-Rio"` no Firefox
- **`F4`**: Colar URL da área de transferência direto no campo de fonte
- **`Esc`**: Pular para o próximo sem salvar

## Depois de terminar
Basta apagar a pasta `triage_ui/` inteira. Os resultados ficam preservados em `data/puc/obm_university_sem_evidencia_manual_triage.csv`.
