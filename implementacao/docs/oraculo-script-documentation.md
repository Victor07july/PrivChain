# Documentação do Script Oráculo de Privacidade (`oraculo.py`)

Este documento detalha o funcionamento e o uso do script `oraculo.py`, uma ferramenta para gerar trajetórias de veículos com privacidade a partir de dados originais.

## Visão Geral

O `oraculo.py` atua como um "oráculo de privacidade por offset". O objetivo principal é receber uma trajetória de um veículo, aplicar um deslocamento geográfico (offset) a essa trajetória e garantir que a nova trajetória (privada) tenha uma diferença de comprimento percentual específica em relação à original.

Este processo ajuda a ofuscar a localização real do veículo, ao mesmo tempo em que preserva um nível de utilidade dos dados para análises de distância. O script gera um hash da trajetória original para fins de auditoria, permitindo a verificação futura sem expor os dados brutos.

## Fluxo de Execução

1.  **Leitura dos Dados**: O script lê um arquivo CSV que contém os dados de trajetória. Ele foi projetado para detectar automaticamente as colunas relevantes (ID do veículo, latitude, longitude, tempo).
2.  **Construção da Trajetória Original**: Para cada veículo no arquivo, o script monta a sequência de pontos (latitude, longitude) que compõem sua trajetória original.
3.  **Busca pelo Melhor Offset**: O núcleo do script é um processo iterativo que tenta encontrar o melhor deslocamento possível. Para cada veículo:
    *   Ele executa um número configurável de tentativas (`--attempts`).
    *   Em cada tentativa, um deslocamento geográfico aleatório (latitude, longitude) é gerado dentro de um raio máximo (`--max-radius-km`).
    *   Este deslocamento é aplicado a todos os pontos da trajetória original.
    *   **Map Matching (Opcional)**: Se ativado (`--enable-map-matching`), a trajetória deslocada é ajustada para se alinhar às estradas mais próximas em um mapa real. Isso torna a trajetória anônima mais realista. Requer as bibliotecas `osmnx` e `shapely`.
4.  **Seleção da Melhor Tentativa**: Após todas as tentativas, o script avalia qual delas produziu uma trajetória cujo comprimento está mais próximo da meta de privacidade percentual (`--target-privacy-percent`). Por exemplo, se a meta é 10%, ele buscará uma trajetória que seja ~10% mais longa ou mais curta que a original.
5.  **Geração de Hash de Auditoria**: Um hash SHA-256 da trajetória original (canônica e ordenada) é calculado. Este hash serve como uma "impressão digital" auditável do dado original, que pode ser registrado (por exemplo, em uma blockchain) para provar a integridade do dado sem revelá-lo.
6.  **Salvamento dos Resultados**: O script gera vários arquivos de saída no diretório especificado (`--output-dir`), incluindo:
    *   Um JSON detalhado com todos os resultados (`oraculo_resultados.json`).
    *   Um CSV de resumo (`oraculo_resumo.csv`).
    *   Um JSON formatado para ferramentas de visualização (`oraculo_trajectories.json`).
    *   Um CSV focado na análise de distâncias (`oraculo_distance_analysis.csv`).
7.  **Envio On-chain (Opcional)**: Se a flag `--send-onchain` for fornecida, o script pode interagir com um smart contract para registrar os resultados da execução (como o hash de auditoria) na blockchain.

## Dependências

-   **Python 3**
-   **pandas**: Para manipulação de dados CSV.
-   **osmnx** e **shapely** (Opcional): Necessárias para a funcionalidade de *map matching*. Se não estiverem instaladas, o script funcionará, mas essa funcionalidade será desativada.

## Como Usar

O script é executado via linha de comando. Abaixo estão os principais argumentos e um exemplo de uso.

### Argumentos

-   `input_csv`: (Obrigatório) Caminho para o arquivo CSV de entrada.
-   `--target-privacy-percent`: (Obrigatório) A meta de diferença percentual absoluta entre a distância da trajetória privada e a original. Ex: `10.0` para 10%.
-   `--attempts`: Número de tentativas de offset aleatório a serem geradas. O padrão é `100`.
-   `--max-radius-km`: O raio máximo em quilômetros para a geração do offset. O padrão é `2.0`.
-   `--enable-map-matching`: Ativa o ajuste da trajetória para a malha viária.
-   `--output-dir`: Diretório onde os arquivos de saída serão salvos. O padrão é `../data/oraculo_offset`.
-   `--vehicle-id`: Filtra a execução para um único ID de veículo.
-   `--seed`: Uma semente para o gerador de números aleatórios, permitindo resultados reproduzíveis.
-   `--send-onchain`: Flag que ativa o envio do resultado para a blockchain.
-   `--private-key`: Chave privada da conta que fará o envio para o contrato. Obrigatório se `--send-onchain` for usado.

### Exemplo de Comando

```bash
python oraculo.py ../data/input_trajectories.csv 
    --target-privacy-percent 15.0 
    --attempts 500 
    --max-radius-km 1.5 
    --enable-map-matching 
    --output-dir ../data/results 
    --seed 42
```

Neste exemplo, o script irá:
-   Ler dados de `../data/input_trajectories.csv`.
-   Tentar gerar uma trajetória privada com uma distância 15% diferente da original.
-   Executar 500 tentativas para cada veículo.
-   Usar um raio de offset máximo de 1.5 km.
-   Ativar o map matching.
-   Salvar os resultados em `../data/results`.
-   Usar a semente `42` para garantir que a aleatoriedade seja a mesma em diferentes execuções.

## Arquivos de Saída

-   `oraculo_resultados.json`: Contém a estrutura de dados completa, incluindo detalhes de cada tentativa, para cada veículo processado.
-   `oraculo_resumo.csv`: Um resumo tabular com as informações mais importantes: IDs dos veículos, distâncias, percentuais de privacidade alcançados e hashes de auditoria.
-   `oraculo_trajectories.json`: Contém as trajetórias originais e privadas em um formato compatível com o script `visualize_trips.py`.
-   `oraculo_distance_analysis.csv`: Um CSV detalhado para análise comparativa das distâncias (SUMO, original, privada).
