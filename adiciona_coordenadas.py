import os
import json
import re
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
from selenium.webdriver.chrome.service import Service
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderQuotaExceeded

DIRETORIO_CEPS = os.path.join(os.path.dirname(__file__), 'cep')
BATCH_SIZE = 10

def obter_coordenadas_nominatim(cep, dados, geolocalizador):
    print(f"[API NOMINATIM] Buscando coordenadas para o CEP: {cep}")
    logradouro = dados.get('logradouro', '')
    bairro = dados.get('bairro', '')
    cidade = dados.get('localidade', '')
    uf = dados.get('uf', '')
    enderecos = [
        f"{logradouro}, {bairro}, {cidade}, {uf}, {cep}",
        f"{logradouro} {cidade} {cep}"
    ]
    formatos = [
        "logradouro, bairro, cidade, uf, cep",
        "logradouro cidade cep"
    ]
    for endereco, formato in zip(enderecos, formatos):
        # print(f"[API NOMINATIM] Tentando formato: {formato} => {endereco}")
        try:
            time.sleep(1)  # O LIMITE DA API É DE 1 REQUISIÇÃO POR SEGUNDO
            localizacao = geolocalizador.geocode(endereco, timeout=10)
            if localizacao:
                # print(f"[API NOMINATIM] Coordenadas encontradas para {cep} com formato '{formato}': {localizacao.latitude}, {localizacao.longitude}")
                return {'latitude': str(localizacao.latitude), 'longitude': str(localizacao.longitude)}
        except (GeocoderTimedOut, GeocoderQuotaExceeded):
            print(f"[API NOMINATIM] Timeout ou limite excedido para {cep}")
        except Exception as e:
            print(f"[API NOMINATIM] Erro: {e}")
    print(f"[API NOMINATIM] Não foi possível encontrar coordenadas para o cep {cep}")
    return None

def obter_coordenadas_site_principal(cep, navegador):
    print(f"[SCRAPING 1] Tentando buscar coordenadas para o cep {cep} no site principal...")
    try:
        url = f"https://site.buscarcep.com.br/?secao=endereco&cep={cep}"
        navegador.get(url)
        time.sleep(0.7)
        navegador.execute_script("window.stop()")
        for _ in range(15):
            html = navegador.page_source
            if 'Cep não encontrado!' in html:
                print(f"[SCRAPING 1] CEP não encontrado no site principal")
                return None
            lat_match = re.search(r'LATITUDE:</strong>\s*([\-\d\.]+)', html)
            lon_match = re.search(r'LONGITUDE:</strong>\s*([\-\d\.]+)', html)
            if lat_match and lon_match:
                # print(f"[SCRAPING 1] Coordenadas encontradas para o cep {cep}: {lat_match.group(1)}, {lon_match.group(1)}")
                return {
                    'latitude': lat_match.group(1),
                    'longitude': lon_match.group(1)
                }
            time.sleep(0.3)
        # print(f"[SCRAPING 1] Não encontrou coordenadas para o cep {cep}.")
        return None
    except Exception as e:
        print(f"[SCRAPING 1] Erro ao buscar o cep {cep}: {e}")
        return None

def obter_coordenadas_site_secundario(cep, navegador):
    print(f"[SCRAPING 2] Tentando buscar coordenadas para o cep {cep} no site secundário...")
    try:
        navegador.get(f"https://www.ruacep.com.br/pesquisa/?q={cep}")
        time.sleep(0.7)
        clicou = False
        for _ in range(1):
            try:
                first_result = WebDriverWait(navegador, 2).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "div.gsc-webResult a.gs-title"))
                )
                first_result.click()
                time.sleep(0.7)
                clicou = True
                break
            except Exception:
                time.sleep(0.2)
        if not clicou:
            # print(f"[SCRAPING 2] Nenhum resultado encontrado para o cep {cep}")
            return None
        tabela = None
        for _ in range(15):
            try:
                WebDriverWait(navegador, 2).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "table.table-striped"))
                )
                html = navegador.page_source
                soup = BeautifulSoup(html, 'html.parser')
                tabela = soup.find('table', class_='table-striped')
                if tabela:
                    linhas = tabela.find_all('tr')
                    lat, lon = None, None
                    for linha in linhas:
                        th = linha.find('th')
                        td = linha.find('td')
                        if th and td:
                            chave = th.get_text().strip().lower()
                            valor = td.get_text().strip()
                            if 'latitude' in chave:
                                lat = valor.split('\n')[0].strip()
                            elif 'longitude' in chave:
                                lon = valor.split('\n')[0].strip()
                    if lat and lon:
                        # print(f"[SCRAPING 2] Coordenadas encontradas para {cep}: {lat}, {lon}")
                        return {'latitude': lat, 'longitude': lon}
                time.sleep(0.3)
            except Exception:
                time.sleep(0.3)
        # print(f"[SCRAPING 2] Não encontrou coordenadas para o cep {cep} no site secundário.")
        return None
    except Exception as e:
        print(f"[SCRAPING 2] Erro ao buscar {cep}: {e}")
        return None

def obter_coordenadas_cep(cep, dados, navegador, geolocalizador):
    print(f"[BUSCA] Iniciando busca para o CEP: {cep}")
    info = obter_coordenadas_nominatim(cep, dados, geolocalizador)
    if info:
        return info
    info = obter_coordenadas_site_principal(cep, navegador)
    if info:
        return info
    info = obter_coordenadas_site_secundario(cep, navegador)
    return info

def main():
    arquivos = [f for f in os.listdir(DIRETORIO_CEPS) if f.endswith('.json')]
    print(f"Total de arquivos encontrados: {len(arquivos)}")
    arquivos = arquivos[:BATCH_SIZE]

    opcoes = webdriver.ChromeOptions()
    opcoes.add_argument('--headless')
    opcoes.add_argument('--no-sandbox')
    opcoes.add_argument('--disable-dev-shm-usage')
    opcoes.add_argument('--disable-gpu')
    opcoes.add_argument('--disable-software-rasterizer')
    opcoes.add_argument('--disable-logging')
    opcoes.add_argument('--disable-extensions')
    servico = Service(log_path=os.devnull)
    navegador = webdriver.Chrome(options=opcoes, service=servico)
    geolocalizador = Nominatim(user_agent="cep_worker_seq")
    caminho_log = os.path.join(os.path.dirname(__file__), f'log.txt')
    ceps_sem_coordenadas = []
    for nome_arquivo in arquivos:
        caminho = os.path.join(DIRETORIO_CEPS, nome_arquivo)
        try:
            with open(caminho, 'r', encoding='utf-8') as f:
                dados = json.load(f)
            if 'logradouro' in dados and 'locker correios' in dados['logradouro'].lower():
                dados['logradouro'] = dados['logradouro'].replace(' - ', ' ').strip()
                dados['logradouro'] = dados['logradouro'].replace('Locker Correios ', '').replace('locker correios ', '').strip()
                dados['logradouro'] = dados['logradouro'].replace(' Entrega Exclusiva', '').replace(' entrega exclusiva', '').strip()
            if 'complemento' in dados and dados['complemento'].strip().lower() == 's/n':
                dados['complemento'] = ''
            if 'latitude' in dados and 'longitude' in dados:
                continue
            cep = dados.get('cep', '')
            if not cep:
                print(f"[ERRO] Arquivo {nome_arquivo} sem campo 'cep'.")
                continue
            info = obter_coordenadas_cep(cep, dados, navegador, geolocalizador)
            if info and 'latitude' in info and 'longitude' in info:
                dados['latitude'] = info['latitude']
                dados['longitude'] = info['longitude']
                with open(caminho, 'w', encoding='utf-8') as f:
                    json.dump(dados, f, ensure_ascii=False, indent=2)
                print(f"[OK] Atualizado: {nome_arquivo}")
            else:
                print(f"[FALHA] Não encontrou coordenadas para o cep {nome_arquivo}")
                ceps_sem_coordenadas.append(nome_arquivo)
        except Exception as e:
            print(f"[ERRO] Erro ao processar o cep {nome_arquivo}: {e}")
            ceps_sem_coordenadas.append(nome_arquivo)
    navegador.quit()

    # Gera relatório final dos ceps sem coordenadas
    if ceps_sem_coordenadas:
        print(f"\n[RESUMO] Arquivos sem coordenadas: {len(ceps_sem_coordenadas)}")
        with open(caminho_log, 'w', encoding='utf-8') as flog:
            for nome in ceps_sem_coordenadas:
                flog.write(f"{nome}\n")
        print(f"[RESUMO] Lista salva em {caminho_log}")
    else:
        print("[RESUMO] Todos os arquivos receberam coordenadas!")

if __name__ == "__main__":
    main() 
