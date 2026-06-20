#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CIRCUIT="$ROOT_DIR/circuits/trajectory_merkle_512.circom"
ARTIFACTS="$ROOT_DIR/artifacts"
PTAU="${PTAU:-$ROOT_DIR/powersOfTau28_hez_final_20.ptau}"

mkdir -p "$ARTIFACTS"

circom "$CIRCUIT" --r1cs --wasm --sym -o "$ARTIFACTS" -l "$ROOT_DIR/node_modules"

snarkjs groth16 setup \
  "$ARTIFACTS/trajectory_merkle_512.r1cs" \
  "$PTAU" \
  "$ARTIFACTS/trajectory_merkle_512_0000.zkey"

snarkjs zkey contribute \
  "$ARTIFACTS/trajectory_merkle_512_0000.zkey" \
  "$ARTIFACTS/trajectory_merkle_512.zkey" \
  --name="local" -v

snarkjs zkey export verificationkey \
  "$ARTIFACTS/trajectory_merkle_512.zkey" \
  "$ARTIFACTS/verification_key.json"

snarkjs zkey export solidityverifier \
  "$ARTIFACTS/trajectory_merkle_512.zkey" \
  "$ARTIFACTS/TrajectoryVerifier.sol"

echo "[ok] Artifacts gerados em $ARTIFACTS"
