# ZKP - Visao Geral

## O que muda com ZKP

O oraculo passa a provar que conhece o trajeto original (sem revelar os pontos). A blockchain aceita a monetizacao apenas se a prova for valida.

## Em termos simples

- O usuario envia o trajeto para o oraculo.
- O oraculo gera uma prova criptografica.
- O contrato verifica a prova e libera a monetizacao.

## Vantagens

- O trajeto nao aparece on-chain.
- A blockchain verifica a autenticidade sem confiar no oraculo.
- Prova nao pode ser reutilizada por outro endereco.

## Desvantagens e custos

- Gerar prova e pesado (tempo e CPU).
- Precisa de setup do circuito (trusted setup).
- Complexidade maior na operacao.

## Limites atuais

- Numero maximo de pontos: 500 (com padding ate 512).
- Para trajetos maiores, sera necessario usar recursao de proofs.

## O que continua igual

- Hash SHA-256 e guardado para auditoria.
- Fluxo de offset e selecao de opcao continua igual.

## Quando usar

- Quando voce quer monetizar sem expor o trajeto.
- Quando precisa de garantia criptografica de posse do trajeto.
