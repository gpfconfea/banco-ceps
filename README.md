# 🌍 Banco de Dados de CEPs com Coordenadas Geográficas

Este projeto estende os dados originais do [OpenCEP](https://github.com/SeuAliado/OpenCEP) (que consolida informações dos Correios e IBGE), adicionando informações geoespaciais.

## 🛠️ Metodologia de Obtenção das Coordenadas
As coordenadas geográficas (latitude e longitude) foram obtidas através de uma metodologia otimizada para maximizar a cobertura, considerando os desafios inerentes à obtenção de dados geoespaciais por CEP.

A tentativa primária é sempre através da API Nominatim, quando a API não fornece um resultado, o script utiliza uma estratégia de web scraping como método complementar.

É importante notar que a confiabilidade e a disponibilidade de coordenadas via scraping para CEPs específicos podem ser variáveis e inconsistentes, dada a dificuldade de encontrar fontes públicas robustas e estáveis para essa informação.

### 1️⃣ API Nominatim (OpenStreetMap via geopy):
Um endereço completo é construído dinamicamente a partir dos campos existentes no JSON (logradouro, bairro, localidade, UF) para otimizar a chance de um resultado preciso.

### 🔁 Fallback via Web Scraping (Estratégia Complementar):
Este método é aplicado para tentar preencher lacunas, mas a completude e a precisão dos dados obtidos por scraping podem variar.

## 🗃️ Estrutura dos Dados
Cada registro de CEP agora inclui os campos latitude e longitude, seguindo o formato:

```JSON
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

## 🚀 Como utilizar
Para acessar e utilizar os dados deste projeto, siga os passos abaixo:

1. Clone este repositório:

```Bash
git clone https://github.com/gpfconfea/banco-ceps.git
cd banco-ceps
```

2. Acesse os arquivos JSON:
Os arquivos JSON modificados com as coordenadas estarão localizados na pasta cep/ dentro do repositório clonado. Você pode importá-los diretamente em suas aplicações ou bancos de dados.

## 🤝 Contribuição
Sua colaboração é muito bem-vinda! Se você encontrar problemas, tiver sugestões de melhoria na metodologia de obtenção de coordenadas, ou quiser contribuir com o código, sinta-se à vontade para:

- Abrir uma issue para relatar bugs.
- Enviar um pull request com suas contribuições de código.
