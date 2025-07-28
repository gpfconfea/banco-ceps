import os
import json
import re
import time
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderQuotaExceeded
from geopy.extra.rate_limiter import RateLimiter
import requests
from dotenv import load_dotenv


DIRETORIO_CEPS = os.path.join(os.path.dirname(__file__), 'cep')

geocode_with_delay = None

load_dotenv()
AWESOME_API_TOKEN = os.getenv('AWESOME_API_TOKEN')

def obter_coordenadas_nominatim(cep, dados):
    print(f"[API NOMINATIM] Buscando coordenadas para o CEP: {cep}")
    logradouro = dados.get('logradouro', '')
    bairro = dados.get('bairro', '')
    cidade = dados.get('localidade', '')
    uf = dados.get('uf', '')
    enderecos = [
        f"{logradouro}, {bairro}, {cidade}, {uf}, {cep}",
        f"{logradouro} {cidade} {cep}"
    ]
    for endereco in enderecos:
        try:
            localizacao = geocode_with_delay(endereco, timeout=10)
            if localizacao:
                return {'latitude': str(localizacao.latitude), 'longitude': str(localizacao.longitude)}
        except (GeocoderTimedOut, GeocoderQuotaExceeded):
            print(f"[API NOMINATIM] Timeout ou limite excedido para {cep}.")
            continue
        except Exception as e:
            print(f"[API NOMINATIM] Erro ao buscar {cep}: {e}")
            continue
    return None

def obter_coordenadas_awesomeapi(cep):
    print(f"[AWESOMEAPI] Buscando coordenadas para o CEP: {cep}")
    if not AWESOME_API_TOKEN:
        print("[AWESOMEAPI] AWESOME_API_TOKEN não está configurado.")
        return None
    
    url = f"https://cep.awesomeapi.com.br/json/{cep}?token={AWESOME_API_TOKEN}"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        if data and data.get('lat') and data.get('lng'):
            return {'latitude': str(data['lat']), 'longitude': str(data['lng'])}
        else:
            return None
    except requests.exceptions.Timeout:
        print(f"[AWESOMEAPI] Timeout ao buscar {cep}.")
        return None
    except requests.exceptions.RequestException as e:
        return None

def obter_coordenadas_site_principal(cep, navegador):
    print(f"[SCRAPING 1] Tentando buscar coordenadas para o cep {cep} no site principal...")
    try:
        url = f"https://site.buscarcep.com.br/?secao=endereco&cep={cep}"
        navegador.get(url)
        time.sleep(0.7)
        navegador.execute_script("window.stop()")
        
        WebDriverWait(navegador, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))
        
        html = navegador.page_source
        if 'Cep não encontrado!' in html:
            print(f"[SCRAPING 1] CEP não encontrado no site principal")
            return None
            
        lat_match = re.search(r'LATITUDE:</strong>\s*([\-\d\.]+)', html)
        lon_match = re.search(r'LONGITUDE:</strong>\s*([\-\d\.]+)', html)
        
        if lat_match and lon_match:
            return {'latitude': lat_match.group(1), 'longitude': lon_match.group(1)}
            
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

def obter_coordenadas_cep(cep, dados, navegador):
    print(f"[BUSCA] Iniciando busca para o CEP: {cep}")
    
    info = obter_coordenadas_nominatim(cep, dados)
    if info:
        return info
    
    info = obter_coordenadas_awesomeapi(cep)
    if info:
        return info

    info = obter_coordenadas_site_principal(cep, navegador)
    if info:
        return info
        
    info = obter_coordenadas_site_secundario(cep, navegador)
    return info


def main():
    global geocode_with_delay

    # Tempo máximo de execução em segundos
    TEMPO_MAXIMO_EXECUCAO_SEGUNDOS = (5 * 3600) # 5 horas
    start_time = time.time()

    log_falhas_path = os.path.join(os.path.dirname(__file__), 'ceps_que_falharam.txt')
    log_sucesso_path = os.path.join(os.path.dirname(__file__), 'ceps_processados_com_sucesso.txt')
    
    ceps_que_falharam = set()
    if os.path.exists(log_falhas_path):
        with open(log_falhas_path, 'r', encoding='utf-8') as f:
            ceps_que_falharam.update(line.strip() for line in f)
    print(f"[INFO] Total de CEPs falhos até a execução anterior: {len(ceps_que_falharam)}")

    ceps_processados_com_sucesso = set()
    if os.path.exists(log_sucesso_path):
        with open(log_sucesso_path, 'r', encoding='utf-8') as f:
            ceps_processados_com_sucesso.update(line.strip() for line in f)
    print(f"[INFO] Total de CEPs com sucesso até a execução anterior: {len(ceps_processados_com_sucesso)}")

    todos_arquivos_json = [f for f in os.listdir(DIRETORIO_CEPS) if f.endswith('.json')]
    print(f"[INFO] Total de arquivos de CEPs a serem verificados: {len(todos_arquivos_json)}")
    
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
    
    geolocalizador_nominatim = Nominatim(user_agent="cep_worker_seq_py")
    geocode_with_delay = RateLimiter(geolocalizador_nominatim.geocode, min_delay_seconds=1.1) 

    novos_ceps_sucesso = []
    novos_ceps_falha = []

    print(f"\nIniciando processamento com tempo limite de {TEMPO_MAXIMO_EXECUCAO_SEGUNDOS}s")
    print("="*100)

    for nome_arquivo in todos_arquivos_json:
        tempo_decorrido = time.time() - start_time
        if tempo_decorrido >= TEMPO_MAXIMO_EXECUCAO_SEGUNDOS:
            print("\n" + "="*100)
            print("[INFO] Tempo máximo de execução atingido. Encerrando o processamento.")
            break

        cep_do_arquivo = nome_arquivo.replace('.json', '').strip()
        
        if cep_do_arquivo in ceps_processados_com_sucesso or cep_do_arquivo in ceps_que_falharam:
            continue

        caminho_completo_arquivo = os.path.join(DIRETORIO_CEPS, nome_arquivo)
        
        try:
            with open(caminho_completo_arquivo, 'r', encoding='utf-8') as f:
                dados = json.load(f)
            
            if 'logradouro' in dados and 'locker correios' in dados['logradouro'].lower():
                dados['logradouro'] = re.sub(r'locker correios|entrega exclusiva|-', '', dados['logradouro'], flags=re.IGNORECASE).strip()
            if 'complemento' in dados and dados['complemento'].strip().lower() == 's/n':
                dados['complemento'] = ''

            cep = dados.get('cep', '').strip()
            if not cep:
                print(f"[ERRO] Arquivo {nome_arquivo} sem campo 'cep'.")
                novos_ceps_falha.append(cep_do_arquivo)
                continue
            
            if 'latitude' in dados and 'longitude' in dados and dados['latitude'] and dados['longitude']:
                print(f"[AVISO] CEP {cep_do_arquivo} já possui coordenadas. Adicionando ao sucesso.")
                novos_ceps_sucesso.append(cep_do_arquivo)
                continue
            
            info = obter_coordenadas_cep(cep, dados, navegador) 
            
            if info and 'latitude' in info and 'longitude' in info:
                dados['latitude'] = info['latitude']
                dados['longitude'] = info['longitude']

                temp_caminho = caminho_completo_arquivo + ".tmp"
                with open(temp_caminho, 'w', encoding='utf-8') as f:
                    json.dump(dados, f, ensure_ascii=False, indent=2)
                os.replace(temp_caminho, caminho_completo_arquivo)
                print(f"[OK] Atualizado: {nome_arquivo}")
                novos_ceps_sucesso.append(cep_do_arquivo)
            else:
                print(f"[FALHA] Não encontrou coordenadas para {nome_arquivo}. Adicionando à lista de falhas.")
                novos_ceps_falha.append(cep_do_arquivo)

        except json.JSONDecodeError:
            print(f"[ERRO] Arquivo JSON inválido: {nome_arquivo}. Adicionando à lista de falhas.")
            novos_ceps_falha.append(cep_do_arquivo)
        except Exception as e:
            print(f"[ERRO] Erro geral ao processar {nome_arquivo}: {e}. Adicionando à lista de falhas.")
            novos_ceps_falha.append(cep_do_arquivo)
    
    navegador.quit()

    if novos_ceps_falha:
        ceps_que_falharam.update(novos_ceps_falha)
        with open(log_falhas_path, 'w', encoding='utf-8') as flog:
            for cep_falho in sorted(list(ceps_que_falharam)):
                flog.write(f"{cep_falho}\n")
    
    if novos_ceps_sucesso:
        ceps_processados_com_sucesso.update(novos_ceps_sucesso)
        with open(log_sucesso_path, 'w', encoding='utf-8') as flog:
            for cep_sucesso in sorted(list(ceps_processados_com_sucesso)):
                flog.write(f"{cep_sucesso}\n")
    
    print("="*100)
    print(f"[INFO] Novo total de CEPs que falharam: {len(ceps_que_falharam)}")
    print(f"[INFO] Novo total de CEPs com sucesso: {len(ceps_processados_com_sucesso)}")
    print("[INFO] Processamento finalizado.")
    print("="*100)

if __name__ == "__main__":
    main()