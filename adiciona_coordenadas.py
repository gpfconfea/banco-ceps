import os
import json
import re
import random
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import time
from multiprocessing import Pool
from selenium.webdriver.chrome.service import Service

CEPS_DIR = os.path.join(os.path.dirname(__file__), 'ceps')
BATCH_SIZE = 100
N_WORKERS = 8

# Lista de user-agents reais para rodízio entre os workers
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
]

def random_delay(a=0.7, b=2.5):
    time.sleep(random.uniform(a, b))

# Função para buscar latitude/longitude no site principal
def get_coordinates_primary(cep, driver):
    try:
        url = f"https://site.buscarcep.com.br/?secao=endereco&cep={cep}"
        driver.get(url)
        random_delay(0.7, 1.5)
        driver.execute_script("window.stop()")
        for _ in range(15):
            html = driver.page_source
            if 'Cep não encontrado!' in html:
                return None
            lat_match = re.search(r'LATITUDE:</strong>\s*([\-\d\.]+)', html)
            lon_match = re.search(r'LONGITUDE:</strong>\s*([\-\d\.]+)', html)
            if lat_match and lon_match:
                return {
                    'latitude': lat_match.group(1),
                    'longitude': lon_match.group(1)
                }
            random_delay(0.3, 0.7)
        return None
    except Exception:
        return None

# Função para buscar latitude/longitude no site secundário
def get_coordinates_secondary(cep, driver):
    try:
        driver.get("https://www.ruacep.com.br/")
        random_delay(0.7, 1.5)
        driver.execute_script("window.stop()")
        search_box = None
        for _ in range(10):
            try:
                search_box = driver.find_element(By.NAME, "q")
                break
            except Exception:
                random_delay(0.2, 0.5)
        if not search_box:
            return None
        search_box.clear()
        random_delay(0.2, 0.5)
        search_box.send_keys(cep)
        random_delay(0.2, 0.5)
        search_button = driver.find_element(By.CSS_SELECTOR, "button.btn-outline-light")
        search_button.click()
        random_delay(0.7, 1.5)
        # Tentar clicar no primeiro resultado do Google Custom Search
        for _ in range(10):
            try:
                first_result = driver.find_element(By.CSS_SELECTOR, "div.gsc-webResult a.gs-title")
                first_result.click()
                random_delay(0.7, 1.5)
                break
            except Exception:
                random_delay(0.2, 0.5)
        # Agora buscar latitude/longitude na página do resultado
        for _ in range(15):
            html = driver.page_source
            soup = BeautifulSoup(html, 'html.parser')
            table = soup.find('table', class_='table-striped')
            if table:
                rows = table.find_all('tr')
                lat, lon = None, None
                for row in rows:
                    th = row.find('th')
                    td = row.find('td')
                    if th and td:
                        key = th.get_text().strip().lower()
                        value = td.get_text().strip()
                        if 'latitude' in key:
                            lat = value.split('\n')[0].strip()
                        elif 'longitude' in key:
                            lon = value.split('\n')[0].strip()
                if lat and lon:
                    return {'latitude': lat, 'longitude': lon}
            random_delay(0.3, 0.7)
        return None
    except Exception:
        return None

def get_cep_coordinates(cep, driver):
    info = get_coordinates_primary(cep, driver)
    if not info:
        info = get_coordinates_secondary(cep, driver)
    return info

def processar_lote(args):
    arquivos, worker_id = args
    options = webdriver.ChromeOptions()
    # options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--log-level=3')
    options.add_argument('--disable-logging')
    options.add_argument('--disable-software-rasterizer')
    # Rotaciona user-agent entre os workers
    user_agent = USER_AGENTS[worker_id % len(USER_AGENTS)]
    options.add_argument(f'user-agent={user_agent}')
    service = Service(log_path=os.devnull)
    driver = webdriver.Chrome(options=options, service=service)
    log_path = os.path.join(os.path.dirname(__file__), f'log_ceps_n_encontrados_{worker_id}.txt')
    for nome_arquivo in arquivos:
        caminho = os.path.join(CEPS_DIR, nome_arquivo)
        try:
            with open(caminho, 'r', encoding='utf-8') as f:
                dados = json.load(f)
            if 'latitude' in dados and 'longitude' in dados:
                continue
            cep = dados.get('cep', '')
            if not cep:
                continue

            random_delay(0.2, 0.7)
            info = get_cep_coordinates(cep, driver)
            if info and 'latitude' in info and 'longitude' in info:
                dados['latitude'] = info['latitude']
                dados['longitude'] = info['longitude']
                with open(caminho, 'w', encoding='utf-8') as f:
                    json.dump(dados, f, ensure_ascii=False, indent=2)
                print(f"[Worker {worker_id}] Atualizado: {nome_arquivo}")
            else:
                print(f"[Worker {worker_id}] Não encontrou coordenadas para {nome_arquivo}")
                with open(log_path, 'a', encoding='utf-8') as flog:
                    flog.write(f"{cep}\n")
        except Exception as e:
            print(f"[Worker {worker_id}] Erro ao processar {nome_arquivo}: {e}")
    driver.quit()

def main():
    arquivos = [f for f in os.listdir(CEPS_DIR) if f.endswith('.json')]
    print(f"Total de arquivos encontrados: {len(arquivos)}")

    # Dividir arquivos entre os workers
    lotes = [[] for _ in range(N_WORKERS)]
    for idx, nome in enumerate(arquivos):
        lotes[idx % N_WORKERS].append(nome)
    args = [(lotes[i], i) for i in range(N_WORKERS) if lotes[i]]
    with Pool(N_WORKERS) as pool:
        pool.map(processar_lote, args)

if __name__ == "__main__":
    main() 