# Mass Benchmark - exemplos de uso

Este guia mostra exemplos de comandos para o script:
`contracts/privacy/implementacao_offset_zkp/scripts/mass_benchmark.py`

Use chaves e seed de exemplo apenas para testes locais. Nao use chaves reais em ambiente publico.

---

## Cenarios disponiveis

| Cenario | Descricao |
|---|---|
| `direct` | Mint assinado pela carteira do usuario (owner); NFT vai para o proprio usuario |
| `pseudonym` | Mint assinado pela carteira do usuario (owner); NFT vai para carteira pseudonima |
| `direct_pseudonym` | Igual ao `pseudonym` — alias para o mesmo fluxo |
| `oracle` | Oraculo **ofusca** o trajeto (offset), calcula monetizacao e registra com ZKP |
| `oracle_direto` | Oraculo registra o trajeto **original** (sem ofuscacao), calcula monetizacao e registra com ZKP |
| `redeem` | Resgata creditos ZK usando a chave real do usuario |
| `redeem_pseudonym` | Resgata creditos ZK usando chave pseudonima (indice HD incrementa a cada resgate) |

Edite a variavel `SCENARIOS` no script para escolher quais cenarios executar:

```python
SCENARIOS = ["oracle", "redeem"]
```

---

## Variaveis de ambiente

### Autorizacao no contrato

O contrato exige `onlyAuthorized` para fazer mint. Sao autorizadas automaticamente:
a carteira que fez o **deploy** (owner) e enderecos registrados via `setAuthorized`.

- Nos cenarios `pseudonym` e `direct_pseudonym`, **quem assina a transacao e
  `BENCH_USER_PRIVATE_KEY`** (deve ser o owner ou autorizada). A carteira pseudonima
  apenas **recebe o NFT como recipient** — nao precisa ser autorizada.
- A chave pseudonima nunca assina transacoes de mint, apenas de resgate (`redeemWithZK`).

### Obrigatorias por cenario

| Variavel | Cenario | Papel |
|---|---|---|
| `BENCH_USER_PRIVATE_KEY` | `direct`, `pseudonym`, `direct_pseudonym`, fallback do `redeem` | Assina a transacao (deve ser owner/autorizada) |
| `BENCH_PSEUDONYM_PRIVATE_KEY` ou `BENCH_PSEUDONYM_SEED_FILE` | `pseudonym`, `direct_pseudonym`, `redeem_pseudonym` | Define o recipient (pseudonimo) ou a carteira de resgate |
| `BENCH_PSEUDONYM_HD_INDEX` | pseudonimo | Indice inicial HD para derivar a carteira (padrao: 0) |
| `BENCH_REDEEM_PRIVATE_KEY` | `redeem` | Chave para resgate (fallback: `BENCH_USER_PRIVATE_KEY`) |
| `BENCH_ORACLE_URL` | `oracle`, `oracle_direto` | URL do oraculo (padrao: `http://127.0.0.1:5001`) |

### Comportamento do pseudonimo

| Configuracao | Comportamento |
|---|---|
| Apenas `BENCH_PSEUDONYM_PRIVATE_KEY` | Chave pseudonima fixa para todas as txs |
| Apenas `BENCH_PSEUDONYM_SEED_FILE` | Deriva via HD wallet; indice incrementa a cada tx |
| Os dois definidos | `BENCH_PSEUDONYM_PRIVATE_KEY` tem prioridade; seed file e ignorado |

Quando usando seed file, o indice real usado em cada tx e:
```
indice_atual = BENCH_PSEUDONYM_HD_INDEX + (numero_da_tx - 1)
```

Exemplo com `BENCH_PSEUDONYM_HD_INDEX=0` e 3 txs:
- tx 1 → indice 0 → endereco A
- tx 2 → indice 1 → endereco B
- tx 3 → indice 2 → endereco C

### Opcionais

| Variavel | Descricao | Padrao |
|---|---|---|
| `BENCH_DEPLOYMENT_FILE` | Caminho do `deployment_info.json` | `implementacao_offset_zkp/deployment_info.json` |
| `BENCH_ORACLE_URL` | URL da API do oraculo | `http://127.0.0.1:5001` |
| `BENCH_MIN_VALUE_MICRO` | Minimo para oraculo quando monetizacao = 0 | `1` |
| `BENCH_DIRECT_MIN_VALUE_MICRO` | Minimo para envio direto quando monetizacao = 0 | `0` |
| `BENCH_GAS_LIMIT` | Gas limit por tx | `900000` |
| `BENCH_RECEIPT_TIMEOUT` | Timeout aguardando recibo (segundos) | `180` |
| `BENCH_REDEEM_LIMIT` | Limita quantidade de resgates (0 = sem limite) | `0` |

> `BENCH_ORACLE_OPTION_INDEX` existe no codigo mas nao e usado — o script escolhe automaticamente a opcao com maior valor.

---

## Variaveis de ambiente do oraculo

Para o oraculo (`scripts/oraculo.py`):

| Variavel | Descricao |
|---|---|
| `ORACLE_DEPLOYMENT_FILE` | Caminho do deployment |
| `ORACLE_PRIVATE_KEY` | Chave privada do oraculo |
| `ORACLE_ZKP_ENABLED` | Ativa ZKP (`0` ou `1`) |
| `ORACLE_ZKP_DIR` | Diretorio ZKP (opcional) |

---

## Colunas medidas por tx

| Coluna | Descricao |
|---|---|
| `tx_seconds` | Tempo ate o oraculo responder HTTP (`confirmar_opcao`) ou tempo total da tx |
| `tx_wait_seconds` | Tempo que o oraculo esperou a confirmacao da blockchain |
| `gas_used` | Gas consumido pela tx |
| `effective_gas_price` | Preco efetivo do gas |
| `tx_fee_wei` | Taxa total paga em wei |
| `oracle_process_seconds` | Tempo do `/processar_trajeto` (so cenario `oracle`) |
| `oracle_confirm_seconds` | Tempo do `/confirmar_opcao` (so cenario `oracle`) |
| `zk_proof_seconds` | Tempo de geracao da prova ZK (lado cliente, so cenario `redeem`/`redeem_pseudonym`) |
| `pseudonym_gen_seconds` | Tempo de derivacao do pseudonimo via HD wallet (so quando usando seed file) |
| `e1_original_micro` / `e1_after_micro` | Valor E1 antes e depois do offset (em micro-BRL) |
| `throughput_tps` | Txs bem-sucedidas / tempo total do cenario (metrica end-to-end conservadora) |

---

## Exemplos

### direct

```bash
export BENCH_USER_PRIVATE_KEY=0xc87509a1c067bbde78beb793e6fa76530b6382a4c0241e5e4a9ec0a0f44dc0d3
export BENCH_DEPLOYMENT_FILE=/home/inmetro/besu-starter-victor/contracts/privacy/implementacao_offset_zkp/deployment_info.json

# SCENARIOS = ["direct"]
python3 /home/inmetro/besu-starter-victor/contracts/privacy/implementacao_offset_zkp/scripts/mass_benchmark.py
```

---

### pseudonym com chave privada direta

```bash
export BENCH_USER_PRIVATE_KEY=0xc87509a1c067bbde78beb793e6fa76530b6382a4c0241e5e4a9ec0a0f44dc0d3  # owner — assina
export BENCH_PSEUDONYM_PRIVATE_KEY=0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d  # recipient
export BENCH_DEPLOYMENT_FILE=/home/inmetro/besu-starter-victor/contracts/privacy/implementacao_offset_zkp/deployment_info.json

# SCENARIOS = ["pseudonym"]
python3 /home/inmetro/besu-starter-victor/contracts/privacy/implementacao_offset_zkp/scripts/mass_benchmark.py
```

> Pseudonimo fixo — o mesmo endereco pseudonimo recebe o NFT em todas as txs.

---

### pseudonym com seed (recipient diferente a cada tx)

Crie o arquivo de seed (uma unica vez):

```bash
python3 -c "
from eth_account import Account
Account.enable_unaudited_hdwallet_features()
account, mnemonic = Account.create_with_mnemonic()
print(mnemonic)
" > /home/inmetro/seed.txt

cat /home/inmetro/seed.txt
```

```bash
export BENCH_USER_PRIVATE_KEY=0xc87509a1c067bbde78beb793e6fa76530b6382a4c0241e5e4a9ec0a0f44dc0d3  # owner — assina
export BENCH_PSEUDONYM_SEED_FILE=/home/inmetro/seed.txt  # recipient derivado por HD
export BENCH_PSEUDONYM_HD_INDEX=0
export BENCH_DEPLOYMENT_FILE=/home/inmetro/besu-starter-victor/contracts/privacy/implementacao_offset_zkp/deployment_info.json

# SCENARIOS = ["pseudonym"]  ou  SCENARIOS = ["direct_pseudonym"]
python3 /home/inmetro/besu-starter-victor/contracts/privacy/implementacao_offset_zkp/scripts/mass_benchmark.py
```

> Recipient diferente a cada tx — indice HD comeca em 0 e incrementa automaticamente.
> `BENCH_USER_PRIVATE_KEY` (owner) assina todas as transacoes.

---

### oracle_direto (sem ofuscacao, com ZKP)

```bash
export BENCH_ORACLE_URL=http://127.0.0.1:5001
export BENCH_MIN_VALUE_MICRO=1
export BENCH_DEPLOYMENT_FILE=/home/inmetro/besu-starter-victor/contracts/privacy/implementacao_offset_zkp/deployment_info.json

# SCENARIOS = ["oracle_direto"]
python3 /home/inmetro/besu-starter-victor/contracts/privacy/implementacao_offset_zkp/scripts/mass_benchmark.py
```

> O oraculo recebe o trajeto original, calcula a monetizacao e registra na blockchain
> com ZKP via `/registrar_trajeto`. Nao ha ofuscacao. O resgate posterior com
> `redeem` ou `redeem_pseudonym` funciona da mesma forma que no cenario `oracle`.

---

### oracle_direto + redeem_pseudonym

```bash
export BENCH_ORACLE_URL=http://127.0.0.1:5001
export BENCH_MIN_VALUE_MICRO=1
export BENCH_PSEUDONYM_SEED_FILE=/home/inmetro/seed.txt
export BENCH_PSEUDONYM_HD_INDEX=0
export BENCH_DEPLOYMENT_FILE=/home/inmetro/besu-starter-victor/contracts/privacy/implementacao_offset_zkp/deployment_info.json

# SCENARIOS = ["oracle_direto", "redeem_pseudonym"]
python3 /home/inmetro/besu-starter-victor/contracts/privacy/implementacao_offset_zkp/scripts/mass_benchmark.py
```

---

### oracle + redeem (carteira real)

```bash
export BENCH_ORACLE_URL=http://127.0.0.1:5001
export BENCH_MIN_VALUE_MICRO=1
export BENCH_REDEEM_PRIVATE_KEY=0xc87509a1c067bbde78beb793e6fa76530b6382a4c0241e5e4a9ec0a0f44dc0d3
export BENCH_DEPLOYMENT_FILE=/home/inmetro/besu-starter-victor/contracts/privacy/implementacao_offset_zkp/deployment_info.json

# SCENARIOS = ["oracle", "redeem"]
python3 /home/inmetro/besu-starter-victor/contracts/privacy/implementacao_offset_zkp/scripts/mass_benchmark.py
```

> O oracle roda primeiro (todos os CSVs), depois o redeem consome a fila gerada.

---

### oracle + redeem_pseudonym (pseudonimo diferente a cada resgate)

```bash
export BENCH_ORACLE_URL=http://127.0.0.1:5001
export BENCH_MIN_VALUE_MICRO=1
export BENCH_PSEUDONYM_SEED_FILE=/home/inmetro/seed.txt
export BENCH_PSEUDONYM_HD_INDEX=0
export BENCH_DEPLOYMENT_FILE=/home/inmetro/besu-starter-victor/contracts/privacy/implementacao_offset_zkp/deployment_info.json

# SCENARIOS = ["oracle", "redeem_pseudonym"]
python3 /home/inmetro/besu-starter-victor/contracts/privacy/implementacao_offset_zkp/scripts/mass_benchmark.py
```

> Cada resgate usa um pseudonimo derivado de um indice HD diferente.

---

### Aviso: redeem e redeem_pseudonym nao podem ser usados juntos

Cada `poseidonRoot` so pode ser resgatado uma vez. Se incluir `redeem` e `redeem_pseudonym` no mesmo `SCENARIOS`, o segundo cenario falhara para todos os itens pois ja foram resgatados pelo primeiro.

Para comparar os dois cenarios, execute em execucoes separadas:

```bash
# Execucao 1: gera mints e resgata com carteira real
# SCENARIOS = ["oracle", "redeem"]

# Execucao 2: gera novos mints e resgata com pseudonimo
# SCENARIOS = ["oracle", "redeem_pseudonym"]
```

---

## Interrupcao

Se cancelar com `Ctrl+C`, o script salva automaticamente um summary parcial com todas as txs concluidas ate o momento. A tx que estava em execucao no momento do cancelamento nao e incluida. O cenario aparece com o sufixo `_interrupted` no CSV.

---

## Arquivos de entrada (DATA_DIR)

O benchmark detecta automaticamente o formato dos arquivos em `DATA_DIR`:

| Padrao de arquivo | Comportamento |
|---|---|
| `vehicles_step_sim_*.csv` | Usado diretamente — CSVs originais do SUMO com todas as colunas |
| `trajeto_*.csv` com colunas extras | Usado diretamente — CSV com informacoes suficientes |
| `trajeto_*.csv` com apenas `lat`/`lon` | **Descartado** — o script busca automaticamente o `trajeto_*.json` correspondente no mesmo diretorio |
| `trajeto_*.json` | Usado diretamente quando nao ha CSV suficiente — gerado pelo oraculo em `data/trajetos_ofuscados/` |

### Usando trajetos ofuscados

Para rodar o benchmark com os trajetos salvos pelo oraculo em `data/trajetos_ofuscados/`,
basta alterar `DATA_DIR` no script:

```python
DATA_DIR = REPO_ROOT / "contracts" / "privacy" / "implementacao_offset_zkp" / "data" / "trajetos_ofuscados"
```

O script detectara que os `trajeto_*.csv` tem apenas `lat`/`lon`, e usara os
`trajeto_*.json` correspondentes automaticamente. Cada JSON contem:
- `trajectory_original` — trajeto original (usado para calcular o hash correto)
- `trajectory_private` — trajeto ofuscado
- `co2_real_g`, `total_distance_km`, `valor_e1_reais` — dados para reconstruir os `contract_params`

---

## Resultados

Os CSVs sao gerados em:
- `test/results/benchmark_results.csv` — todas as linhas (tx + summary)
- `test/results/benchmark_summary.csv` — apenas os resumos por cenario