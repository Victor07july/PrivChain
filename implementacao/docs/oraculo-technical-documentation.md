# Documentação Técnica do Script `oraculo.py`

Este documento fornece uma análise técnica detalhada da arquitetura, algoritmos e componentes do script `oraculo.py`.

## 1. Arquitetura Geral

O script opera em um fluxo sequencial por veículo, projetado para ser modular e extensível. A arquitetura pode ser dividida nas seguintes camadas:

1.  **Interface de Linha de Comando (CLI)**: Gerenciada pelo módulo `argparse`, define a interface pública do script, controlando todos os parâmetros de execução.
2.  **Orquestração do Processo**: A função `main()` atua como o orquestrador principal, validando argumentos, configurando o ambiente (ex: `random.seed`) e invocando a camada de processamento de dados.
3.  **Processamento de Dados (CSV)**: A função `process_csv()` gerencia a leitura, pré-processamento e agrupamento dos dados do CSV de entrada usando a biblioteca `pandas`. Ela itera sobre cada veículo e dispara a lógica de privacidade.
4.  **Lógica de Privacidade (Core)**: A função `evaluate_attempts()` contém a lógica central do oráculo. Para uma única trajetória, ela gera e avalia múltiplas trajetórias candidatas "privadas".
5.  **Módulos de Algoritmo**: Um conjunto de funções puras que implementam os algoritmos específicos, como cálculo de distância (`haversine_km`), geração de offset (`generate_random_offset`), e map matching (`maybe_map_match`).
6.  **Saída e Persistência**: A função `save_outputs()` é responsável por serializar os resultados em diferentes formatos (JSON, CSV) e salvá-los em disco.
7.  **Módulo On-chain (Opcional)**: O `blockchain_sender.py` é um módulo desacoplado, importado e utilizado apenas quando a funcionalidade de envio para a blockchain é ativada.

## 2. Componentes e Funções Principais

### `process_csv(...)`

-   **Responsabilidade**: Orquestrar a leitura e o processamento do arquivo de entrada.
-   **Detalhes**:
    -   Utiliza `pd.read_csv()` para carregar os dados.
    -   Chama `detect_columns()` para encontrar dinamicamente os nomes das colunas de `vehicle_id`, `lat`, `lon`, `time`, etc. Isso confere flexibilidade ao formato do CSV de entrada.
    -   Garante uma ordem de processamento estável dos pontos da trajetória ordenando-os por `time`, `end_time` e, finalmente, pela ordem original da linha (`_row_order`).
    -   Agrupa o DataFrame por `vehicle_id` usando `df.groupby()`.
    -   Para cada grupo (veículo), chama `build_trajectory_from_group()` para extrair a lista de pontos `[[lat, lon], ...]` e, em seguida, invoca `evaluate_attempts()`.

### `evaluate_attempts(...)`

-   **Responsabilidade**: Encontrar a melhor trajetória privada para um único veículo.
-   **Algoritmo**:
    1.  Calcula a distância total da trajetória original (`orig_km`) usando `trajectory_distance_km`.
    2.  Entra em um loop de `1` a `attempts`.
    3.  Em cada iteração:
        a.  Chama `generate_random_offset()` para obter um deslocamento geográfico aleatório.
        b.  Aplica este offset a todos os pontos da trajetória original com `apply_offset()`.
        c.  Se o map matching estiver ativo, a trajetória deslocada é passada para `maybe_map_match()`.
        d.  Calcula a distância da nova trajetória privada (`private_km`).
        e.  Calcula a diferença percentual (`diff`) e o erro absoluto em relação à meta (`error_to_target`).
        f.  Armazena todos os dados da tentativa em uma lista `tries`.
    4.  Após o loop, encontra o dicionário em `tries` com o menor valor na chave `error_to_target_percent`. Esta é a "melhor tentativa".
    5.  Chama `build_audit_hash()` para gerar o hash da trajetória original.
    6.  Monta e retorna a estrutura de dados final do resultado, contendo os dados da melhor tentativa, métricas de privacidade e distâncias.

### `generate_random_offset(...)`

-   **Responsabilidade**: Gerar um ponto de offset aleatório uniformemente distribuído dentro de um círculo.
-   **Algoritmo**:
    -   `angle = random.uniform(0.0, 2.0 * math.pi)`: Seleciona um ângulo aleatório.
    -   `distance_km = math.sqrt(random.uniform(0.0, 1.0)) * max_radius_km`: Seleciona uma distância. O uso de `math.sqrt()` é crucial para garantir que a distribuição de pontos seja uniforme na área do círculo, evitando a concentração de pontos perto do centro.
    -   Converte as coordenadas polares (ângulo, distância) em offsets cartesianos (dx, dy) em quilômetros.
    -   Converte os offsets em km para graus de latitude e longitude, ajustando o offset de longitude com base no cosseno da latitude de referência para compensar a convergência dos meridianos.

### `maybe_map_match(...)` e `snap_point_to_road(...)`

-   **Responsabilidade**: Ajustar uma trajetória aos segmentos de estrada mais próximos em um mapa real.
-   **Algoritmo**:
    1.  Verifica se as dependências (`osmnx`, `shapely`) estão disponíveis.
    2.  Baixa o grafo da malha viária para a região em torno do centro da trajetória usando `ox.graph_from_point()`. O grafo é baixado uma vez por trajetória para otimizar o desempenho.
    3.  Para cada ponto da trajetória deslocada, `snap_point_to_road()` é chamada:
        a.  `ox.distance.nearest_edges()` encontra a aresta (segmento de estrada) mais próxima do ponto.
        b.  A geometria dessa aresta (uma `LineString` da biblioteca `shapely`) é obtida.
        c.  `edge_geom.project(Point(lon, lat))` projeta o ponto na linha infinita que contém o segmento de estrada.
        d.  `edge_geom.interpolate(...)` encontra o ponto exato *dentro* do segmento de estrada que corresponde à projeção. Isso resulta em um ajuste muito preciso.
        e.  Retorna as novas coordenadas `[lat, lon]` do ponto ajustado.

### `build_audit_hash(...)`

-   **Responsabilidade**: Criar um hash SHA-256 determinístico e auditável de uma trajetória.
-   **Algoritmo**:
    1.  Cria um dicionário Python contendo o `vehicle_id` e a trajetória original normalizada (pontos arredondados para 7 casas decimais).
    2.  Serializa este dicionário para uma string JSON usando `json.dumps()`.
    3.  Os parâmetros `sort_keys=True` e `separators=(",", ":")` são críticos. Eles garantem que a mesma estrutura de dados produza sempre a **exata mesma string** (representação canônica), independentemente da ordem interna das chaves no Python.
    4.  A string canônica é encodada para `utf-8` e passada para o `hashlib.sha256()`.

## 3. Estruturas de Dados

A principal estrutura de dados é o dicionário de resultado retornado por `evaluate_attempts`. Este dicionário é então salvo no arquivo `oraculo_resultados.json`.

```json
{
  "vehicle_id": "string",
  "timestamp_utc": "string (ISO 8601)",
  "audit": {
    "original_hash_sha256": "string",
    "hash_algorithm": "SHA-256"
  },
  "privacy": {
    "target_percent": "float",
    "best_diff_percent": "float",
    "best_abs_diff_percent": "float",
    "error_to_target_percent": "float"
  },
  "distance": {
    "sumo_km": "float | null",
    "original_km": "float",
    "private_km": "float"
  },
  "trajectory": {
    "original": "List[List[float]]",
    "private": "List[List[float]]",
    "private_json": "string (JSON aninhado)"
  },
  "best_attempt": {
    "attempt": "int",
    "offset": {
      "offset_lat_deg": "float",
      "offset_lon_deg": "float",
      "distance_km": "float",
      "angle_deg": "float"
    }
  },
  "attempts": "List[Dict]" // Contém os detalhes de todas as tentativas
}
```

-   **`trajectory.private_json`**: Este campo é uma string contendo o JSON da trajetória privada. É uma redundância criada para facilitar a passagem do dado como um único argumento para chamadas de contrato em blockchain.
-   **`attempts`**: Uma lista grande e detalhada de cada tentativa realizada. Incluída para permitir análises mais profundas sobre o processo de busca, mas pode ser removida das saídas se o volume de dados for um problema.

## 4. Interação com Blockchain (`--send-onchain`)

-   Quando a flag `--send-onchain` é usada, a função `main` importa dinamicamente `send_oracle_results` do módulo `blockchain_sender`.
-   A função `send_oracle_results` (não presente em `oraculo.py`) é responsável por:
    1.  Ler o endereço do contrato e a ABI do arquivo de deployment (`deployment_file`).
    2.  Conectar-se a um nó da blockchain (provavelmente via Web3.py).
    3.  Iterar sobre os `results` do oráculo.
    4.  Para cada resultado, construir uma transação para o método do contrato especificado (`--method-name`).
    5.  Mapear os dados do resultado para os argumentos do método, conforme especificado por `--method-arg`. Este mapeamento permite extrair valores do JSON de resultado usando uma notação de "ponto" (ex: `$.audit.original_hash_sha256`).
    6.  Assinar a transação com a chave privada fornecida (`--private-key`) e enviá-la para a rede.
