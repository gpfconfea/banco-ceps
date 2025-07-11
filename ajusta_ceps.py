import os
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

CEPS_DIR = os.path.join(os.path.dirname(__file__), 'ceps')

def processar_arquivo(nome_arquivo):
    caminho = os.path.join(CEPS_DIR, nome_arquivo)
    try:
        with open(caminho, 'r', encoding='utf-8') as f:
            dados = json.load(f)
        cep = dados.get('cep', '')
        cep_sem_traco = cep.replace('-', '')
        if cep != cep_sem_traco:
            dados['cep'] = cep_sem_traco
            with open(caminho, 'w', encoding='utf-8') as f:
                json.dump(dados, f, ensure_ascii=False, indent=2)
            return f"Corrigido: {nome_arquivo} -> {cep} para {cep_sem_traco}"
    except Exception as e:
        return f"Erro ao processar {nome_arquivo}: {e}"
    return None

def ajustar_ceps():
    arquivos = [f for f in os.listdir(CEPS_DIR) if f.endswith('.json')]
    print(f"Total de arquivos encontrados: {len(arquivos)}")

    with ThreadPoolExecutor() as executor:
        futuros = [executor.submit(processar_arquivo, nome) for nome in arquivos]
        for futuro in as_completed(futuros):
            resultado = futuro.result()
            if resultado:
                print(resultado)

if __name__ == "__main__":
    ajustar_ceps()
