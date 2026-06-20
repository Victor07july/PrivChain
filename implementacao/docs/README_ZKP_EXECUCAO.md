# ZKP - Execucao (comandos)

Este README descreve os comandos para compilar o circuito, gerar o verificador, fazer deploy e executar o oraculo com ZK.

## 1) Pre-requisitos

- Node.js 18+
- circom (binario no PATH)
- Python 3.10+
- RPC Ethereum/Besu acessivel
- powersOfTau ptau (ex: powersOfTau28_hez_final_20.ptau)

## 2) Compilar circuito e gerar artifacts

```bash
cd contracts/privacy/implementacao_offset_zkp/zkp
npm install
PTAU=$PWD/powersOfTau28_hez_final_20.ptau npm run build
```

Artifacts gerados em: 
- zkp/artifacts/trajectory_merkle_512.zkey
- zkp/artifacts/trajectory_merkle_512_js/trajectory_merkle_512.wasm
- zkp/artifacts/TrajectoryVerifier.sol

## 3) Deploy do Verifier (Groth16)

```bash
cd contracts/privacy/implementacao_offset_zkp
  python3 scripts/deploy_verifier.py \
    --contract-file zkp/artifacts/TrajectoryVerifier.sol \
    --contract-name Groth16Verifier \
    --output-file zkp/verifier_deployment.json \
    --rpc-url http://localhost:8545 \
  --private-key 0xSUA_CHAVE
```

## 4) Deploy do contrato principal

```bash
cd contracts/privacy/implementacao_offset_zkp
python3 scripts/deploy_e1.py \
  --output-file deployment_info.json \
  --rpc-url http://localhost:8545 \
  --private-key 0xSUA_CHAVE
```

## 5) Configurar o Verifier no contrato

```bash
cd contracts/privacy/implementacao_offset_zkp
python3 scripts/set_verifier.py \
  --rpc-url http://localhost:8545 \
  --main-deploy deployment_info.json \
  --verifier-deploy zkp/verifier_deployment.json \
  --private-key 0xSUA_CHAVE
```

## 6) Autorizar carteira do usuario (necessario para envio direto sem offset)

```bash
cd contracts/privacy/implementacao_offset_zkp
python3 scripts/set_authorized.py \
  --rpc-url http://localhost:8545 \
  --deployment-file deployment_info.json \
  --user-private-key 0xSUA_CHAVE
```

## 7) Financiar o contrato para resgate ZK

O resgate ZK paga a partir do saldo do contrato. Envie ETH para o contrato
antes de testar o resgate.

```bash
cd contracts/privacy/implementacao_offset_zkp
python3 scripts/fund_contract.py \
  --deployment-file deployment_info.json \
  --amount-eth 100 \
  --private-key 0xSUA_CHAVE
```

## 8) Executar o oraculo com ZK

```bash
export ORACLE_DEPLOYMENT_FILE=/home/inmetro/besu-starter-victor/contracts/privacy/implementacao_offset_zkp/deployment_info.json
export ORACLE_PRIVATE_KEY="0xc87509a1c067bbde78beb793e6fa76530b6382a4c0241e5e4a9ec0a0f44dc0d3"
export ORACLE_ZKP_DIR=/home/inmetro/besu-starter-victor/contracts/privacy/implementacao_offset_zkp/zkp
export ORACLE_ZKP_ENABLED=1
python3 oraculo.py --host 127.0.0.1 --port 5001
```

## 9) Executar o cliente (envio/mint)

```bash
python3 usuario.py \
  contracts/privacy/implementacao_offset_zkp/data/trajetos/vehicles_step_sim_1.csv \
  --oracle-url http://127.0.0.1:5001 \
  --deployment-file contracts/privacy/implementacao_offset_zkp/deployment_info.json \
  --user-private-key 0xSUA_CHAVE
```

## 10) Resgatar com ZK (lendo o CSV original)

```bash
python3 contracts/privacy/implementacao_offset_zkp/scripts/usuario.py \
  contracts/privacy/implementacao_offset_zkp/data/trajetos/vehicles_step_sim_1.csv \
  --deployment-file contracts/privacy/implementacao_offset_zkp/deployment_info.json \
  --user-private-key 0xSUA_CHAVE
```

No prompt, escolha "Resgatar" (R). O script gera a prova ZK localmente e
chama `redeemWithZK` na blockchain.

## Observacoes

- Para desabilitar ZK no oraculo: `export ORACLE_ZKP_ENABLED=0`.
- O limite de pontos e 500 (com padding ate 512).
- Se mudar circuito, gere novos artifacts e redeploy o Verifier.
- O resgate ZK exige os artifacts locais (use `ORACLE_ZKP_DIR` ou `--zkp-dir`).
- O resgate ZK e unico e queima o NFT associado ao poseidonRoot.
