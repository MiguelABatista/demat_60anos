import requests
import pandas as pd
import time

all_data = []

# O IMC começou em 1994. O loop vai até 2025.
for year in range(1994, 2026):
    url = f"https://www.imc-math.org.uk/?act=results&by=sum&year={year}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    
    print(f"Coletando dados do ano {year}...")
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        try:
            # Extrai todas as tabelas da página
            tables = pd.read_html(response.text)
            
            if tables:
                # Geralmente a tabela de resultados é a principal/primeira com dados úteis
                df = tables[0] 
                df['Year'] = year # Adiciona a coluna do ano para identificação
                all_data.append(df)
        except ValueError:
            print(f"Nenhuma tabela encontrada para {year}.")
    else:
        print(f"Falha ao acessar o ano {year}. Status: {response.status_code}")
        
    # Pausa de 1 segundo entre requisições para evitar bloqueio por excesso de tráfego
    time.sleep(1)

# Junta todos os anos e salva no CSV
if all_data:
    final_df = pd.concat(all_data, ignore_index=True)
    final_df.to_csv('imc_results_all_years.csv', index=False, encoding='utf-8')
    print("Download concluído! Arquivo salvo como 'imc_results_all_years.csv'.")
else:
    print("Nenhum dado pôde ser extraído.")