# ZKP - Documentacao Tecnica (Offset + Trajetoria)

## Objetivo

Provar em ZK que o oraculo conhece o trajeto original associado ao hash on-chain, sem revelar os pontos. A prova e verificada no contrato no momento da monetizacao.

## Componentes

- Oraculo (Python): gera a prova ZK e envia a transacao.
- Prover (Node.js): gera o proof via snarkjs.
- Circuito (circom): calcula root Poseidon a partir dos pontos.
- Contrato (Solidity): verifica o proof e grava root + hash SHA-256.

## Hashes on-chain

- `originalTrajectoryHash`: SHA-256 para auditoria externa.
- `poseidonTrajectoryRoot`: root ZK-friendly para verificacao.

## Circuito

Arquivo: zkp/circuits/trajectory_merkle_512.circom

Parametros fixos:
- TOTAL_POINTS = 512 (padding)
- MAX_POINTS = 500 (validado no prover)
- CHUNK_SIZE = 8 pontos por chunk
- LEAF_COUNT = 64

Algoritmo dentro do circuito:
1. Leaf: `leaf_i = Poseidon(lat_i, lon_i, i)`
2. Chunk: `chunk_j = Poseidon(leaf_{j*8} ... leaf_{j*8+7})`
3. Merkle: hashing em camadas ate `root`
4. Public inputs: `root`, `recipient`, `nonce`

## Prover (Node.js)

Arquivo: zkp/scripts/prove.js

Entrada JSON (exemplo):
```json
{
  "points": [[-23.55, -46.63], [-23.56, -46.64]],
  "recipient": "0x1234...abcd",
  "nonce": 1715800000000000000,
  "max_points": 500,
  "scale": 10000000
}
```

Saida JSON:
```json
{
  "poseidon_root": "0x...",
  "public_signals": {
    "root": "...",
    "recipient": "...",
    "nonce": "..."
  },
  "proof": {
    "a": ["...", "..."],
    "b": [["...", "..."], ["...", "..."]],
    "c": ["...", "..."]
  }
}
```

## Geracao de artifacts

No diretorio zkp:

```bash
npm install
PTAU=/caminho/para/powersOfTau28_hez_final_20.ptau npm run build
```

Artifacts gerados:
- zkp/artifacts/trajectory_merkle_512.zkey
- zkp/artifacts/trajectory_merkle_512_js/trajectory_merkle_512.wasm
- zkp/artifacts/TrajectoryVerifier.sol

## Contrato Solidity

Arquivo: contract/CarbonCreditNFT_E1.sol

Funcao principal:
```solidity
function mintWithOracleValueZK(
    uint256 oracleE1Value,
    address recipient,
    bytes32 originalTrajectoryHash,
    bytes32 poseidonRoot,
    uint256 nonce,
    uint256[2] calldata proofA,
    uint256[2][2] calldata proofB,
    uint256[2] calldata proofC
) external returns (uint256 tokenId, uint256 e1Value)
```

Verificacao:
- `zkVerifier.verifyProof(a, b, c, [root, recipient, nonce])`
- nullifier anti-replay: `keccak256(poseidonRoot, recipient, nonce)`

## Deploy do Verifier

1. Gere o Verifier:
   - `snarkjs zkey export solidityverifier ...`
2. Compile e faça deploy do Verifier.
3. Chame `setZkVerifier(address)` no contrato principal.

## Oraculo

Arquivo: scripts/oraculo.py

Configuracao:
- `ORACLE_ZKP_DIR`: caminho para `implementacao_offset_zkp/zkp`
- `ORACLE_ZKP_ENABLED`: `1` (default) ou `0` para desabilitar

Fluxo:
1. `confirmar_opcao` gera proof via Node.
2. Envia transacao `mintWithOracleValueZK` com proof e root.

## Bibliotecas

- Node: `snarkjs`, `circomlibjs`
- Circom: `poseidon.circom`
- Python: `subprocess`, `web3.py`
- Solidity: verificador Groth16 (BN254)

## Observacoes

- O circuito usa padding ate 512 pontos.
- O root Poseidon e independente do SHA-256; ambos sao armazenados.
- Para trajetorias muito maiores, e recomendavel adicionar recursao de proofs.
