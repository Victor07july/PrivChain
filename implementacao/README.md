# implementacao — Privacy Oracle + ZKP + Carbon Credit NFT

This module implements a privacy-preserving trajectory monetisation system on top of the PrivChain Besu network.

## How it works

```
Vehicle CSV  ─►  Oracle (oraculo.py)  ─►  Offset trajectory  ─►  ZKP Proof  ─►  CarbonCreditNFT (on-chain)
                      │                                                  │
                      └── SHA-256 audit hash ──────────────────────────►┘
```

1. **The oracle** (`scripts/oraculo.py`) receives raw GPS trajectory data (CSV from SUMO simulator).
2. It generates many random geographic offset candidates and selects the one whose total travel distance is closest to a privacy target (e.g. 15 % deviation from the original).
3. It computes a **SHA-256 audit hash** of the original trajectory (canonical JSON, deterministic).
4. It runs as an HTTP server. The **user client** (`scripts/usuario.py`) connects to it, submits trajectories, and receives the offset result.
5. If ZKP is enabled, the oracle generates a **Groth16 zero-knowledge proof** using the compiled circom circuit and the `snarkjs` library. The proof proves trajectory ownership without revealing the raw GPS points.
6. The user calls `mintWithPrivacy` (offset only) or `redeemWithZK` (ZKP flow) on the **CarbonCreditNFT** smart contract, which mints an ERC-721 NFT representing the verified trajectory.

## Directory Structure

```
implementacao/
├── contract/
│   ├── CarbonCreditNFT_E1.sol   # ERC-721 with privacy oracle integration
│   └── package.json              # npm package for @openzeppelin dependency
├── scripts/
│   ├── oraculo.py                # Privacy oracle HTTP server (main entry point)
│   ├── usuario.py                # User client (mint / redeem)
│   ├── blockchain_sender.py      # Decoupled on-chain sender module
│   ├── deploy_e1.py              # Deploy CarbonCreditNFT
│   ├── deploy_verifier.py        # Deploy Groth16 verifier contract
│   ├── set_verifier.py           # Wire verifier into main contract
│   ├── set_authorized.py         # Authorize a wallet for direct minting
│   ├── fund_contract.py          # Fund contract for ZK redemption payouts
│   ├── hd_wallet.py              # HD wallet utilities
│   ├── mass_benchmark.py         # Batch benchmark runner
│   └── plot/                     # Result plotting scripts
├── zkp/
│   ├── circuits/
│   │   └── trajectory_merkle_512.circom   # ZKP circuit definition
│   ├── artifacts/
│   │   ├── TrajectoryVerifier.sol         # Generated Solidity verifier
│   │   ├── trajectory_merkle_512.zkey     # Proving key
│   │   ├── trajectory_merkle_512_js/      # WASM witness generator
│   │   └── verification_key.json          # Verification key
│   ├── scripts/
│   │   ├── build.sh                       # Compile circuit + generate artifacts
│   │   └── prove.js                       # Generate proof from witness
│   └── package.json
├── data/
│   ├── trajetos/                  # Input CSV files (SUMO vehicle simulation)
│   └── oraculo_offset/            # Example oracle output (JSON)
├── docs/
│   ├── README_ZKP_EXECUCAO.md     # Step-by-step ZKP commands
│   ├── zkp-overview.md            # ZKP conceptual overview
│   ├── zkp-technical.md           # ZKP technical deep-dive
│   ├── oraculo-technical-documentation.md
│   └── MASS_BENCHMARK.md
└── deployment_info.json           # Created after deploy_e1.py (gitignored)
```

## Prerequisites

### Python dependencies

```bash
pip install pandas web3 eth-account requests
```

Optional (map matching — snaps trajectory to real roads):

```bash
pip install osmnx shapely
```

### Node.js dependencies (for ZKP only)

```bash
# In the zkp/ directory
cd zkp && npm install

# In the contract/ directory (for @openzeppelin)
cd contract && npm install
```

### External tools (for ZKP circuit recompilation only)

- **circom** 2.x — circuit compiler ([installation](https://docs.circom.io/getting-started/installation/))
- **snarkjs** — included via `npm install` in `zkp/`
- **Powers of Tau** file — `powersOfTau28_hez_final_20.ptau` (see Recompiling section below)

> **Note:** Pre-compiled artifacts are already present in `zkp/artifacts/`. You only need the above tools if you want to modify and recompile the circuit.

---

## Step-by-Step Setup

### Step 1 — Start the Besu network

From the repository root:

```bash
./run.sh
```

Wait until `list.sh` shows all services are up. The RPC endpoint will be at `http://localhost:8545`.

### Step 2 — Install smart contract dependencies

```bash
cd implementacao/contract
npm install
```

### Step 3 — Deploy the ZKP verifier contract

```bash
cd implementacao
python3 scripts/deploy_verifier.py \
  --contract-file zkp/artifacts/TrajectoryVerifier.sol \
  --contract-name Groth16Verifier \
  --output-file zkp/verifier_deployment.json \
  --rpc-url http://localhost:8545 \
  --private-key 0xYOUR_PRIVATE_KEY
```

### Step 4 — Deploy the main CarbonCreditNFT contract

```bash
cd implementacao
python3 scripts/deploy_e1.py \
  --output-file deployment_info.json \
  --rpc-url http://localhost:8545 \
  --private-key 0xYOUR_PRIVATE_KEY
```

This creates `deployment_info.json` with the contract address.

### Step 5 — Wire the verifier into the main contract

```bash
cd implementacao
python3 scripts/set_verifier.py \
  --rpc-url http://localhost:8545 \
  --main-deploy deployment_info.json \
  --verifier-deploy zkp/verifier_deployment.json \
  --private-key 0xYOUR_PRIVATE_KEY
```

### Step 6 — Authorize a user wallet

```bash
cd implementacao
python3 scripts/set_authorized.py \
  --rpc-url http://localhost:8545 \
  --deployment-file deployment_info.json \
  --user-private-key 0xUSER_PRIVATE_KEY
```

### Step 7 — Fund the contract (ZKP redemption only)

The ZKP redemption path pays out from the contract balance. Send ETH to the contract before testing:

```bash
cd implementacao
python3 scripts/fund_contract.py \
  --deployment-file deployment_info.json \
  --amount-eth 100 \
  --private-key 0xYOUR_PRIVATE_KEY
```

### Step 8 — Start the oracle server

```bash
cd implementacao/scripts

# With ZKP enabled:
export ORACLE_DEPLOYMENT_FILE=../deployment_info.json
export ORACLE_PRIVATE_KEY="0xYOUR_PRIVATE_KEY"
export ORACLE_ZKP_DIR=../zkp
export ORACLE_ZKP_ENABLED=1
python3 oraculo.py --host 127.0.0.1 --port 5001

# Without ZKP (offset-only mode):
export ORACLE_ZKP_ENABLED=0
python3 oraculo.py --host 127.0.0.1 --port 5001
```

The oracle listens for trajectory submissions and returns the privacy-offset result along with an optional ZKP proof.

### Step 9 — Submit a trajectory (user client)

```bash
cd implementacao/scripts
python3 usuario.py \
  ../data/trajetos/vehicles_step_sim_1.csv \
  --oracle-url http://127.0.0.1:5001 \
  --deployment-file ../deployment_info.json \
  --user-private-key 0xUSER_PRIVATE_KEY
```

When prompted, choose:
- **M** → Mint with privacy offset (oracle mode)
- **R** → Redeem with ZKP proof (generates proof locally, calls `redeemWithZK`)

---

## Oracle Without On-Chain Sending

You can run the oracle in standalone mode (no blockchain) to explore the offset algorithm:

```bash
cd implementacao/scripts
python3 oraculo.py \
  ../data/trajetos/vehicles_step_sim_1.csv \
  --target-privacy-percent 15 \
  --attempts 100 \
  --max-radius-km 2.0 \
  --output-dir ../data/oraculo_offset
```

**Output files** (in `--output-dir`):
- `oraculo_resultados.json` — full per-vehicle result with all candidate attempts
- `oraculo_resumo.csv` — best attempt summary per vehicle
- `oraculo_trajectories.json` — offset trajectories in visualisation format
- `oraculo_distance_analysis.csv` — original vs. offset distance comparison

---

## Recompiling the ZKP Circuit

Only needed if you modify `zkp/circuits/trajectory_merkle_512.circom`:

```bash
# Download the Powers of Tau file (one-time setup, ~1 GB)
wget https://hermez.s3-eu-west-1.amazonaws.com/powersOfTau28_hez_final_20.ptau \
  -O zkp/powersOfTau28_hez_final_20.ptau

cd zkp
npm install
PTAU=$PWD/powersOfTau28_hez_final_20.ptau npm run build
```

New artifacts will be written to `zkp/artifacts/`. After recompiling, re-deploy the verifier (Steps 3 and 5).

---

## Key Parameters

| Parameter | Default | Description |
|---|---|---|
| `--target-privacy-percent` | 15 | Target deviation (%) from original trajectory distance |
| `--attempts` | 100 | Number of random offset candidates to generate |
| `--max-radius-km` | 2.0 | Maximum offset radius in kilometers |
| `--enable-map-matching` | off | Snap offset trajectory to real road network (requires `osmnx`) |
| `--search-radius-m` | 1500 | Road-snapping search radius in meters |
| `ORACLE_ZKP_ENABLED` | 0 | Set to `1` to enable ZKP proof generation |

---

## Privacy Model

The system operates under a **trusted oracle** model with optional cryptographic guarantees:

| Feature | Offset only | Offset + ZKP |
|---|---|---|
| Raw GPS hidden from blockchain | Yes | Yes |
| Oracle must be trusted | Yes | No — proof verifies without trust |
| On-chain proof of trajectory ownership | No | Yes (Groth16) |
| Proof reuse prevention | No | Yes (proof bound to user address) |
| Computational cost | Low | High (proof generation ~10–60 s depending on hardware) |

The **audit hash** (SHA-256 of the original trajectory in canonical JSON form) is stored on-chain in both modes, allowing future auditors to verify that a specific trajectory was submitted without revealing the raw points.

---

## Contract: CarbonCreditNFT_E1

The main contract (`contract/CarbonCreditNFT_E1.sol`) is an ERC-721 token with the following key methods:

| Method | Who calls | Description |
|---|---|---|
| `mintWithPrivacy(...)` | Authorised user | Mint NFT with offset trajectory hash |
| `redeemWithZK(proof, publicSignals, ...)` | Any user | Mint NFT using on-chain ZKP verification |
| `setVerifier(address)` | Owner | Set the Groth16 verifier contract address |
| `setAuthorized(address, bool)` | Owner | Grant/revoke direct mint permission |

---

## Notes

- The ZKP circuit supports a maximum of **500 trajectory points** (padded to 512 for the Merkle tree).
- The ZKP proving key (`trajectory_merkle_512.zkey`) must match the deployed `TrajectoryVerifier.sol`. If you recompile the circuit, redeploy the verifier.
- To disable ZKP at runtime: `export ORACLE_ZKP_ENABLED=0`.
- Test wallets use the standard development mnemonic (`abandon abandon ... about`). **Never use these keys on mainnet or any public network.**
