# PrivChain

A private Hyperledger Besu blockchain network with a privacy-preserving trajectory oracle and Zero-Knowledge Proof (ZKP) based carbon credit smart contract.

## Overview

PrivChain combines:

- **Hyperledger Besu** – permissioned EVM-compatible blockchain running the QBFT consensus algorithm
- **Tessera** – private transaction manager for confidential on-chain data
- **Auth service** – FastAPI + PostgreSQL service that issues JWT tokens accepted by Besu's RPC authentication layer
- **Nginx** – reverse proxy with TLS termination in front of all services
- **Quorum Explorer** – block explorer UI
- **Offset Oracle** – trusted oracle that applies geographic offset to vehicle trajectories before sending data on-chain
- **ZKP Verifier** – Groth16 zero-knowledge proof system that lets users prove trajectory ownership without revealing raw GPS points
- **CarbonCreditNFT** – ERC-721 smart contract that mints carbon credit tokens upon validated trajectory submission

## Repository Structure

```
PrivChain/
├── docker-compose.yml      # Full network (Besu + Tessera + Auth + Nginx + Explorer)
├── run.sh                  # Start the network
├── stop.sh                 # Stop all containers
├── remove.sh               # Tear down containers and volumes
├── restart.sh              # Stop, wait, and resume
├── resume.sh               # Resume a stopped network
├── list.sh                 # Print all service endpoints
├── .env.example            # Root environment variables template → copy to .env
├── config/
│   ├── besu/               # Genesis files (QBFT/IBFT/Clique), node config, public RSA key
│   ├── nodes/              # Per-node key material (validators, members, rpcnode)
│   ├── tessera/            # Tessera private transaction manager config
│   ├── tls/                # RSA key pair for JWT auth (private key gitignored)
│   ├── nginx/              # Nginx config; SSL certs go in nginx/ssl/ (gitignored)
│   └── ethsigner/          # EthSigner key management
├── auth/                   # FastAPI authentication service
│   ├── docker-compose.yml  # auth-db + auth-service + auth-service-init
│   └── src/config/
│       └── .env.example    # Auth service environment template → copy to .env
├── quorum-explorer/        # Block explorer configuration
│   └── .env.example        # Explorer environment template → copy to .env
└── implementacao/          # Privacy oracle + ZKP + smart contract
    └── README.md           # Full setup and usage guide
```

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) 20.10+
- [Docker Compose](https://docs.docker.com/compose/) v2+
- `openssl` (for key and certificate generation)

The `implementacao/` module has additional Python and Node.js requirements — see [implementacao/README.md](implementacao/README.md).

---

## Setup

Follow these steps in order before running `./run.sh` for the first time.

### Step 1 — Root environment file

```bash
cp .env.example .env
```

The defaults in `.env.example` work for local development. Edit if you need to pin specific image versions or change the consensus algorithm.

### Step 2 — Besu logging environment

```bash
cp config/besu/.env.example config/besu/.env
```

This file only sets the Log4J config path. No secrets; safe to leave as-is.

### Step 3 — Generate the RSA key pair for JWT authentication

Besu's RPC endpoint requires a JWT signed with an RSA private key. The auth service signs tokens with the private key; Besu verifies them with the public key.

```bash
# Generate 4096-bit RSA private key
openssl genrsa -out private.pem 4096

# Extract the public key
openssl rsa -in private.pem -pubout -out public.pem

# Install private key in both locations used at runtime
cp private.pem auth/src/config/web3/privateRSAKey.pem
cp private.pem config/tls/privateRSAKey.pem

# Install public key (already committed as placeholder; replace with yours)
cp public.pem config/besu/publicRSAKey.pem
cp public.pem config/tls/publicRSAKey.pem

# Remove temp files
rm private.pem public.pem
```

> The private keys are gitignored. The public keys in `config/besu/` and `config/tls/` are tracked and pre-populated with a development placeholder — replace them with your generated key for a fresh deployment.

### Step 4 — Auth service environment

```bash
cp auth/src/config/.env.example auth/src/config/.env
```

Then open `auth/src/config/.env` and set:

| Variable | Description |
|---|---|
| `JWT_SECRET` | Random secret for the auth service's own JWT signing (`openssl rand -hex 32`) |
| `DB_PASSWORD` | PostgreSQL password (must match `auth/docker-compose.yml`) |
| `BESU_JWT_PRIVATE_KEY` | Paste the full content of `auth/src/config/web3/privateRSAKey.pem` as a single-line string with `\n` escapes, or load it from the file in `auth/src/config/web3/setup.py` |

### Step 5 — Nginx SSL certificate

Nginx serves all traffic over HTTPS. Place your certificate files in `config/nginx/ssl/` (gitignored).

**Self-signed certificate for local development:**

```bash
mkdir -p config/nginx/ssl

openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout config/nginx/ssl/nginx-selfsigned.key \
  -out    config/nginx/ssl/nginx-selfsigned.crt \
  -subj "/C=BR/ST=RJ/L=Rio de Janeiro/O=PrivChain/CN=localhost"
```

For production, place your CA-issued `.crt` and `.key` files here and update `config/nginx/nginx.conf` accordingly.

### Step 6 — Quorum Explorer environment

```bash
cp quorum-explorer/.env.example quorum-explorer/.env
```

Then set `NEXTAUTH_SECRET` to a fresh random value:

```bash
openssl rand -hex 32
# paste the output into quorum-explorer/.env as NEXTAUTH_SECRET=<value>
```

---

## Running the Network

### Start

```bash
./run.sh
```

On first run Docker will pull images (a few minutes). When all containers are up, the script prints all service endpoints:

| Service | URL |
|---|---|
| JSON-RPC HTTP | `http://localhost:8545` |
| JSON-RPC WebSocket | `ws://localhost:8546` |
| Block Explorer | `http://localhost:25000/explorer/nodes` |
| Auth service | `http://localhost:80/auth` (via Nginx) |

### Stop (keep data)

```bash
./stop.sh
```

### Resume after stop

```bash
./resume.sh
```

### Restart

```bash
./restart.sh
```

### Tear down (delete all data)

```bash
./remove.sh
```

---

## Network Topology

| Node | Role |
|---|---|
| `validator1`–`validator4` | Block producers (QBFT consensus) |
| `member1`–`member3` | Private transaction senders (each paired with a Tessera node) |
| `rpcnode` | Public JSON-RPC endpoint |
| `rpcnode-admin` | Administrative JSON-RPC endpoint (JWT-protected) |

Private transactions between member nodes are encrypted end-to-end by **Tessera**. Only the designated recipients can decrypt the payload; the public ledger only sees a transaction hash.

---

## Consensus Algorithm

Configured in `.env`:

```bash
BESU_CONS_ALGO=QBFT   # default
# Other options: IBFT, CLIQUE
```

---

## Node Key Material

The `config/nodes/` directory contains pre-generated development keys for all nodes. These keys define the network identity (genesis block validator set, static-nodes.json, Tessera public keys) and must be present for the network to boot.

> **Warning:** these are development-only keys with no value on any public network. Never use them to hold real assets. For a production deployment, generate fresh keys with `besu operator generate-blockchain-config` and update the genesis file accordingly.

---

## Sensitive Files Reference

| File | Gitignored | How to create |
|---|---|---|
| `.env` | Yes | `cp .env.example .env` |
| `config/besu/.env` | Yes | `cp config/besu/.env.example config/besu/.env` |
| `config/tls/privateRSAKey.pem` | Yes | `openssl genrsa` (Step 3) |
| `auth/src/config/web3/privateRSAKey.pem` | Yes | Copy from Step 3 |
| `config/nginx/ssl/` | Yes | `openssl req -x509 ...` (Step 5) |
| `auth/src/config/.env` | Yes | `cp auth/src/config/.env.example auth/src/config/.env` |
| `quorum-explorer/.env` | Yes | `cp quorum-explorer/.env.example quorum-explorer/.env` |

Files that are safe to commit and are tracked:

| File | Notes |
|---|---|
| `config/besu/publicRSAKey.pem` | RSA public key — used by Besu to verify JWTs |
| `config/tls/publicRSAKey.pem` | Same public key — used by Tessera/Nginx TLS config |
| `config/nodes/*/nodekey.pub` | P2P public identity of each node |
| `config/nodes/*/tm.pub`, `tma.pub` | Tessera public encryption keys |
| `config/nodes/*/address` | Ethereum address of each node's account |
| `config/nodes/*/accountKeystore` | Encrypted keystore (dev password `Password1`) |

---

## Privacy Oracle and ZKP

See [implementacao/README.md](implementacao/README.md) for full details on deploying the smart contract, running the privacy oracle, and executing ZKP-based trajectory redemptions.

---

## License

Apache 2.0
