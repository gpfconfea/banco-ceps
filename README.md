# Banco de Dados de CEPs com Coordenadas Geográficas  

Modificação dos arquivos JSON do [OpenCEP](https://github.com/SeuAliado/OpenCEP) para incluir latitude e longitude.  

## Sobre  
Dados dos correios ibge e CEP reunidos pelo OpenCEP, agora com a adição dos campos `latitude` e `longitude` aos CEPs. 

## Metodologia de Obtenção das Coordenadas

1. **API Nominatim (OpenStreetMap via geopy):**
   - O script tenta obter latitude e longitude usando a API Nominatim, montando o endereço completo a partir dos dados do JSON.

2. **Fallback via Web Scraping:**
   - Caso a API não retorne resultado, o script recorre ao scraping de sites públicos para tentar obter as coordenadas.

## 📊 Estrutura dos Dados  

```json
{
  "cep": "01001000",
  "logradouro": "Praça da Sé",
  "complemento": "lado ímpar",
  "bairro": "Sé",
  "localidade": "São Paulo",
  "uf": "SP",
  "ibge": "3550308",
  "latitude": "-23.5498772",
  "longitude": "-46.6339869"
}
```
