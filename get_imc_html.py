import requests
import time

def baixar_htmls_imc(ano_inicio=1994, ano_fim=2025):
    for ano in range(ano_inicio, ano_fim + 1):
        url = f"https://www.imc-math.org.uk/?year={ano}&section=results&item=bysum"
        
        print(f"Baixando {ano}...")
        resposta = requests.get(url)
        
        if resposta.status_code == 200:
            with open(f"imc_{ano}.html", "w", encoding="utf-8") as f:
                f.write(resposta.text)
        else:
            print(f"Falha no ano {ano}: {resposta.status_code}")
            
        time.sleep(1)

if __name__ == "__main__":
    baixar_htmls_imc(1994, 2025)