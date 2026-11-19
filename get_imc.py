import requests
import pandas as pd
import time
from io import StringIO
from pathlib import Path

output_dir = Path('imc_results')
output_dir.mkdir(exist_ok=True)


def fetch_html(year):
    url = f"https://www.imc-math.org.uk/?act=results&by=sum&year={year}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"Falha ao acessar o ano {year}. Status: {response.status_code}")
        return None
    return response.text


def parse_table(html):
    tables = pd.read_html(StringIO(html))
    for df in tables:
        df.columns = df.columns.astype(str).str.strip()
        # If header row ended up as data (integer columns), promote first row
        if df.columns[0] == '0':
            df.columns = df.iloc[0].astype(str).str.strip()
            df = df.iloc[1:].reset_index(drop=True)
        if 'Sum' in df.columns:
            return df
    return None


def clean_table(df):
    df = df.rename(columns={'D1': 'Day1', 'D2': 'Day2'})
    df = df[pd.to_numeric(df['Sum'], errors='coerce').notna()]
    df = df.loc[:, ~df.columns.str.startswith('Unnamed')]
    return df


def save_year(df, year):
    path = output_dir / f'imc_results_{year}.csv'
    df.to_csv(path, index=False, encoding='utf-8')
    print(f"Arquivo salvo: {path}")


def collect_year(year):
    print(f"Coletando dados do ano {year}...")
    html = fetch_html(year)
    if html is None:
        return None
    if True:
        df = parse_table(html)
        if df is None:
            print(f"Nenhuma tabela encontrada para {year}.")
            return None
        print(f"Colunas: {list(df.columns)}")
        df = clean_table(df)
        df['Year'] = year
        save_year(df, year)
        return df
    # except (ValueError, KeyError) as e:
    #     print(f"Erro ao processar {year}: {e}")
    #     return None

def main():
    all_data = []
    for year in range(2019, 2020):
        df = collect_year(year)
        if df is not None:
            all_data.append(df)
        time.sleep(1)

    if all_data:
        final_df = pd.concat(all_data, ignore_index=True)
        final_df.to_csv(output_dir / 'imc_results_all_years.csv', index=False, encoding='utf-8')
        print("Download concluído! Arquivo salvo como 'imc_results/imc_results_all_years.csv'.")
    else:
        print("Nenhum dado pôde ser extraído.")

if __name__ == "__main__":
    main()