import pandas as pd

def extrair_e_guardar_tabela(ficheiro_html, ficheiro_csv):
    # Lê todas as tabelas presentes no ficheiro HTML
    tabelas = pd.read_html(ficheiro_html)
    
    # Seleciona a tabela com mais linhas (tabela de resultados principal)
    df_principal = max(tabelas, key=len)
    
    # Guarda o dataframe num ficheiro CSV
    df_principal.to_csv(ficheiro_csv, index=False, encoding='utf-8')

if __name__ == "__main__":
    ficheiro_entrada = 'imc_2019.html'
    ficheiro_saida = 'resultados_imc_2019.csv'
    
    extrair_e_guardar_tabela(ficheiro_entrada, ficheiro_saida)