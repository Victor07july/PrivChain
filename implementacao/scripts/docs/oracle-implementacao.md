# Oracle de Privacidade por Offset - Implementacao

## Escopo

Este documento descreve como o sistema esta implementado hoje, com foco operacional.

Arquivos principais:

- Servidor API: contracts/privacy/implementacao_offset/scripts/oraculo.py
- Cliente: contracts/privacy/implementacao_offset/scripts/usuario.py
- Sender reutilizavel: contracts/privacy/implementacao_offset/scripts/blockchain_sender.py
- Contrato: contracts/privacy/implementacao_offset/contract/CarbonCreditNFT_E1.sol

Diagramas PUML:

- [oracle-componentes.puml](oracle-componentes.puml)
- [oracle-sequencia-envio.puml](oracle-sequencia-envio.puml)
- [oracle-sequencia-resgate.puml](oracle-sequencia-resgate.puml)

## Servidor Oraculo

Natureza:

- API FastAPI com uvicorn.
- Endpoints: POST /processar_trajeto, POST /confirmar_opcao, GET /health.

Configuracao por ambiente:

- ORACLE_DEPLOYMENT_FILE
- ORACLE_PRIVATE_KEY

Comportamento:

1. /processar_trajeto
   - valida hash recebido contra hash recalculado.
   - executa N tentativas de offset.
   - calcula valor original e valor deslocado simulado.
   - aplica cap 10% + bonus nas opcoes deslocadas.
   - retorna Top K por menor diferenca absoluta.
   - salva opcoes pendentes em memoria por request_id.

2. /confirmar_opcao
   - recupera request_id no cache em memoria.
   - envia mintWithOracleValue no contrato.
   - usa carteira do oraculo como recipient.
   - remove pendencia apos confirmar.

## Cliente usuario.py

Ao iniciar, o cliente pergunta a operacao:

- Enviar (fluxo ja existente)
- Resgatar (novo fluxo)

### Modo Enviar

- Com offset:
  - envia trajetoria + hash para o oraculo.
  - recebe Top 5 opcoes estimadas.
  - usuario confirma opcao.
  - oraculo grava on-chain.

- Sem offset:
  - envia direto para contrato com calculateAndMintWithHash.
  - exibe monetizacao estimada sem deslocamento.

### Modo Resgatar

- usuario informa hash alvo.
- cliente consulta isTrajectoryHashRegistered(hash).
- usuario escolhe carteira real ou pseudonima.
- cliente envia requestRedeemByHash(hash, pseudonym).
- retorno principal e tx_hash (evento de resgate).

## Contrato Solidity

Funcoes relevantes de envio:

- calculateAndMintWithHash(params, recipient, originalHash)
- mintWithOracleValue(oracleE1Value, recipient, originalHash)

Funcoes relevantes de hash/resgate:

- verifyOriginalTrajectoryHash(tokenId, providedHash)
- isTrajectoryHashRegistered(providedHash)
- requestRedeemByHash(providedHash, pseudonym)

Persistencia de hash:

- todo mint com originalHash != 0x0 marca registeredTrajectoryHashes[hash] = true.

## Execucao rapida

Servidor:

python3 contracts/privacy/implementacao_offset/scripts/oraculo.py --host 127.0.0.1 --port 5000

Cliente (enviar):

python3 contracts/privacy/implementacao_offset/scripts/usuario.py \
  caminho/arquivo.csv \
  --deployment-file contracts/privacy/implementacao_offset/deployment_info.json \
  --user-private-key 0xSUA_CHAVE

Cliente (resgatar com carteira pseudonima predefinida):

python3 contracts/privacy/implementacao_offset/scripts/usuario.py \
  --deployment-file contracts/privacy/implementacao_offset/deployment_info.json \
  --user-private-key 0xCHAVE_REAL \
  --pseudonym-private-key 0xCHAVE_PSEUDONIMA

## Observacoes de producao

- Cache de pendencias do oraculo e em memoria; para alta disponibilidade, mover para Redis/DB.
- Proteger chaves privadas fora de codigo/repositorio.
- Restringir endpoint de confirmacao por autenticacao/autorizacao.
