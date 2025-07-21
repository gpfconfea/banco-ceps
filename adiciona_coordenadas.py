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
from geopy.extra.rate_limiter import RateLimiter

DIRETORIO_CEPS = os.path.join(os.path.dirname(__file__), 'cep')
BATCH_SIZE = 6000

geocode_with_delay = None

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

def obter_coordenadas_site_principal(cep, navegador):
    print(f"[SCRAPING 1] Tentando buscar coordenadas para o cep {cep} no site principal...")
    try:
        url = f"https://site.buscarcep.com.br/?secao=endereco&cep={cep}"
        navegador.get(url)
        time.sleep(0.7)
        navegador.execute_script("window.stop()")
        
        try:
            WebDriverWait(navegador, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "body")) 
            )
        except Exception as e:
            print(f"[SCRAPING 1] Página do site principal não carregou a tempo para {cep}: {e}")
            return None

        html = navegador.page_source
        if 'Cep não encontrado!' in html:
            print(f"[SCRAPING 1] CEP não encontrado no site principal")
            return None
        lat_match = re.search(r'LATITUDE:</strong>\s*([\-\d\.]+)', html)
        lon_match = re.search(r'LONGITUDE:</strong>\s*([\-\d\.]+)', html)
        if lat_match and lon_match:
            return {
                'latitude': lat_match.group(1),
                'longitude': lon_match.group(1)
            }
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
    info = obter_coordenadas_site_principal(cep, navegador)
    if info:
        return info
    info = obter_coordenadas_site_secundario(cep, navegador)
    return info

def main():
    global geocode_with_delay

    log_falhas_path = os.path.join(os.path.dirname(__file__), 'ceps_que_falharam.txt')
    log_sucesso_path = os.path.join(os.path.dirname(__file__), 'ceps_processados_com_sucesso.txt')
    
    ceps_que_falharam = set()
    if os.path.exists(log_falhas_path):
        with open(log_falhas_path, 'r', encoding='utf-8') as f:
            for line in f:
                ceps_que_falharam.add(line.strip())
    print(f"[INFO] Total de CEPs falhos até a execução anterior: {len(ceps_que_falharam)}")

    ceps_processados_com_sucesso = set()
    if os.path.exists(log_sucesso_path):
        with open(log_sucesso_path, 'r', encoding='utf-8') as f:
            for line in f:
                ceps_processados_com_sucesso.add(line.strip())
    print(f"[INFO] Total de CEPs com sucesso até a execução anterior: {len(ceps_processados_com_sucesso)}")

    todos_arquivos_json = [f for f in os.listdir(DIRETORIO_CEPS) if f.endswith('.json')]
    print(f"[INFO] Total de arquivos de CEPs: {len(todos_arquivos_json)}")
    
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
    
    geolocalizador_nominatim = Nominatim(user_agent="cep_worker_seq")
    geocode_with_delay = RateLimiter(geolocalizador_nominatim.geocode, min_delay_seconds=1.1) 

    tentativas_nesta_rodada = 0
    
    novos_ceps_sucesso = []
    novos_ceps_falha = []

    print(f"\nIniciando processamento. BATCH_SIZE: {BATCH_SIZE}")

    for nome_arquivo in todos_arquivos_json:
        if tentativas_nesta_rodada >= BATCH_SIZE:
            print("\n")
            print("="*100)
            print(f"[INFO] Limite de {BATCH_SIZE} tentativas atingido. Encerrando o processamento do lote.")
            break

        cep_do_arquivo = nome_arquivo.replace('.json', '').strip()
        caminho_completo_arquivo = os.path.join(DIRETORIO_CEPS, nome_arquivo)

        if cep_do_arquivo in ceps_processados_com_sucesso:
            continue
        if cep_do_arquivo in ceps_que_falharam:
            continue

        try:
            with open(caminho_completo_arquivo, 'r', encoding='utf-8') as f:
                dados = json.load(f)
            
            if 'logradouro' in dados and 'locker correios' in dados['logradouro'].lower():
                dados['logradouro'] = dados['logradouro'].replace(' - ', ' ').strip()
                dados['logradouro'] = dados['logradouro'].replace('Locker Correios ', '').replace('locker correios ', '').strip()
                dados['logradouro'] = dados['logradouro'].replace(' Entrega Exclusiva', '').replace(' entrega exclusiva', '').strip()
            if 'complemento' in dados and dados['complemento'].strip().lower() == 's/n':
                dados['complemento'] = ''

            cep = dados.get('cep', '').strip()
            if not cep:
                print(f"[ERRO] Arquivo {nome_arquivo} sem campo 'cep'.")
                novos_ceps_falha.append(cep_do_arquivo)
                tentativas_nesta_rodada += 1
                continue
            
            if 'latitude' in dados and 'longitude' in dados and dados['latitude'] and dados['longitude']:
                print(f"[AVISO] CEP {cep_do_arquivo} já possui coordenadas. -> Adicionando ao log de sucesso e pulando busca.")
                novos_ceps_sucesso.append(cep_do_arquivo)
                continue
            
            tentativas_nesta_rodada += 1 

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
                print(f"[FALHA] Não encontrou coordenadas para o cep {nome_arquivo} nesta rodada. Adicionando à lista de falhas.")
                novos_ceps_falha.append(cep_do_arquivo)
        except json.JSONDecodeError:
            print(f"[ERRO] Arquivo JSON inválido: {nome_arquivo}. Adicionando à lista de falhas.")
            novos_ceps_falha.append(cep_do_arquivo)
            tentativas_nesta_rodada += 1
        except Exception as e:
            print(f"[ERRO] Erro geral ao processar o cep {nome_arquivo}: {e}. Adicionando à lista de falhas.")
            novos_ceps_falha.append(cep_do_arquivo)
            tentativas_nesta_rodada += 1
    
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
    
    print(f"[INFO] Novo total de CEPs que falharam: {len(ceps_que_falharam)}")
    print(f"[INFO] Novo total de CEPs com sucesso: {len(ceps_processados_com_sucesso)}")
    print("="*100)

if __name__ == "__main__":
    main()
