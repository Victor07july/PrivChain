# Oracle de Privacidade por Offset - Conceito

## Objetivo

Separar privacidade de localização e monetizacao on-chain sem perder auditabilidade.

Em termos simples:

- O usuario decide se quer deslocar o trajeto (offset) ou enviar direto.
- O oraculo calcula opcoes de privacidade e monetizacao estimada.
- A blockchain registra o valor final e o hash da trajetoria original.
- O hash permite auditoria posterior sem expor o trajeto em claro.

## Ideia central

O sistema aplica o principio de minimizacao de exposicao:

- Para negociacao de privacidade, usa trajetos deslocados.
- Para vinculo auditavel, usa somente hash da trajetoria original.

Assim, o dado sensivel nao precisa ser persistido integralmente no contrato.

## Componentes e papeis

- Cliente usuario
  - Orquestra a experiencia local.
  - Pode enviar com offset, sem offset, ou solicitar resgate por hash.

- Oraculo API
  - Recebe trajeto + hash.
  - Simula N tentativas de deslocamento.
  - Retorna Top 5 por menor diferenca absoluta de distancia.
  - Aplica limite de monetizacao para nunca ultrapassar o original.

- Contrato Solidity
  - Calcula e/ou armazena valor monetizado.
  - Armazena hash original por token.
  - Mantem indice de hashes registrados para verificacao e resgate.

## Regra economica

Cada opcao deslocada passa por um teto:

- Base = 90% do valor do trajeto original.
- Bonus = ate 10% proporcional a diferenca de trajeto.
- Valor final = minimo entre valor bruto deslocado e teto.

Consequencia: o deslocado nunca supera o original.

## Diagramas Mermaid

### Arquitetura logica

```mermaid
flowchart LR
    U[Usuario Local] --> C[Cliente usuario.py]
    C -->|POST /processar_trajeto| O[Oraculo FastAPI]
    O -->|Top 5 opcoes + estimativas| C
    C -->|POST /confirmar_opcao| O
    O -->|mintWithOracleValue| B[(Contrato CarbonCreditNFT_E1)]
    C -->|Sem offset: calculateAndMintWithHash| B
    C -->|Resgate por hash: requestRedeemByHash| B
```

### Sequencia conceitual de envio com offset

```mermaid
sequenceDiagram
    participant U as Usuario
    participant C as Cliente
    participant O as Oraculo
    participant S as Contrato

    U->>C: Escolhe enviar com offset
    C->>O: trajetoria + hash original
    O->>O: gera N tentativas e Top 5
    O-->>C: opcoes + monetizacao estimada
    U->>C: escolhe opcao
    C->>O: confirmar_opcao(request_id, option)
    O->>S: mintWithOracleValue(valorFinal, carteiraOraculo, hashOriginal)
    S-->>O: tx confirmada
    O-->>C: tx_hash + valor final
```

### Sequencia conceitual de resgate por hash

```mermaid
sequenceDiagram
    participant U as Usuario
    participant C as Cliente
    participant S as Contrato

    U->>C: Escolhe Resgatar
    U->>C: Informa hash + modo real/pseudonimo
    C->>S: isTrajectoryHashRegistered(hash)
    S-->>C: true/false
    C->>S: requestRedeemByHash(hash, pseudonym)
    S-->>C: evento HashRedeemRequested
```

## Garantias e limites

- Garantias
  - Vinculo auditavel por hash original.
  - Cap de monetizacao no fluxo com offset.
  - Confirmacao explicita antes de gravar no caminho do oraculo.

- Limites atuais
  - Pendencias do oraculo ficam em memoria de processo.
  - Em restart, request_id pendente pode ser perdido.
