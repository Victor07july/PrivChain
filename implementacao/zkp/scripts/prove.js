import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import * as snarkjs from "snarkjs";
import { buildPoseidon } from "circomlibjs";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const TOTAL_POINTS = 512;
const DEFAULT_MAX_POINTS = 500;
const DEFAULT_SCALE = 1e7;
const SHIFT_LAT = 90;
const SHIFT_LON = 180;

function parseArgs(argv) {
    const args = {};
    for (let i = 2; i < argv.length; i++) {
        const key = argv[i];
        if (!key.startsWith("--")) {
            continue;
        }
        const value = argv[i + 1];
        args[key.slice(2)] = value;
        i += 1;
    }
    return args;
}

function toBytes32Hex(value) {
    const big = BigInt(value);
    let hex = big.toString(16);
    if (hex.length > 64) {
        throw new Error("Value exceeds 32 bytes");
    }
    hex = hex.padStart(64, "0");
    return `0x${hex}`;
}

function encodeCoord(value, shift, scale) {
    const rounded = Math.round(value * scale);
    const shiftScaled = Math.round(shift * scale);
    return BigInt(rounded + shiftScaled);
}

function buildArrays(points, maxPoints, scale) {
    if (points.length > maxPoints) {
        throw new Error(`points length ${points.length} exceeds max_points ${maxPoints}`);
    }
    if (points.length > TOTAL_POINTS) {
        throw new Error(`points length ${points.length} exceeds TOTAL_POINTS ${TOTAL_POINTS}`);
    }

    const lat = new Array(TOTAL_POINTS).fill(0n);
    const lon = new Array(TOTAL_POINTS).fill(0n);

    for (let i = 0; i < points.length; i++) {
        const [rawLat, rawLon] = points[i];
        lat[i] = encodeCoord(Number(rawLat), SHIFT_LAT, scale);
        lon[i] = encodeCoord(Number(rawLon), SHIFT_LON, scale);
    }

    return { lat, lon };
}

function poseidonHash(poseidon, inputs) {
    return poseidon.F.toObject(poseidon(inputs));
}

function computeRoot(poseidon, lat, lon) {
    const leaf = new Array(TOTAL_POINTS);
    for (let i = 0; i < TOTAL_POINTS; i++) {
        leaf[i] = poseidonHash(poseidon, [lat[i], lon[i], BigInt(i)]);
    }

    const chunk = new Array(64);
    for (let j = 0; j < 64; j++) {
        const inputs = [];
        for (let k = 0; k < 8; k++) {
            inputs.push(leaf[j * 8 + k]);
        }
        chunk[j] = poseidonHash(poseidon, inputs);
    }

    let level = chunk;
    while (level.length > 1) {
        const next = new Array(level.length / 2);
        for (let i = 0; i < next.length; i++) {
            next[i] = poseidonHash(poseidon, [level[2 * i], level[2 * i + 1]]);
        }
        level = next;
    }

    return level[0];
}

function logStep(message, startMs) {
    const elapsed = ((Date.now() - startMs) / 1000).toFixed(2);
    console.log(`[prove] ${message} (${elapsed}s)`);
}

async function main() {
    const startMs = Date.now();
    const args = parseArgs(process.argv);
    if (!args.input || !args.output) {
        throw new Error("Usage: node prove.js --input input.json --output output.json [--artifacts dir]");
    }

    const inputPath = path.resolve(args.input);
    const outputPath = path.resolve(args.output);
    const artifactsDir = args.artifacts
        ? path.resolve(args.artifacts)
        : path.resolve(__dirname, "..", "artifacts");

    const wasmPath = path.join(
        artifactsDir,
        "trajectory_merkle_512_js",
        "trajectory_merkle_512.wasm"
    );
    const zkeyPath = path.join(artifactsDir, "trajectory_merkle_512.zkey");

    if (!fs.existsSync(wasmPath) || !fs.existsSync(zkeyPath)) {
        throw new Error("Artifacts nao encontrados. Rode: npm run build");
    }

    const payload = JSON.parse(fs.readFileSync(inputPath, "utf-8"));
    const points = payload.points || [];
    const recipient = payload.recipient;
    const nonce = payload.nonce !== undefined ? payload.nonce.toString() : undefined;
    const maxPoints = payload.max_points || DEFAULT_MAX_POINTS;
    const scale = payload.scale || DEFAULT_SCALE;

    if (!recipient || nonce === undefined) {
        throw new Error("recipient e nonce sao obrigatorios");
    }

    console.log("[prove] Preparando inputs...");
    const arrays = buildArrays(points, maxPoints, scale);
    logStep("Inputs preparados", startMs);

    console.log("[prove] Calculando Poseidon root...");
    const poseidon = await buildPoseidon();
    const root = computeRoot(poseidon, arrays.lat, arrays.lon);
    logStep("Poseidon root calculado", startMs);

    const input = {
        lat: arrays.lat.map((v) => v.toString()),
        lon: arrays.lon.map((v) => v.toString()),
        recipient: BigInt(recipient).toString(),
        nonce: BigInt(nonce).toString(),
        root: root.toString(),
    };

    console.log("[prove] Gerando prova Groth16...");
    const { proof, publicSignals } = await snarkjs.groth16.fullProve(
        input,
        wasmPath,
        zkeyPath
    );
    logStep("Prova gerada", startMs);

    console.log("[prove] Exportando calldata...");
    const callData = await snarkjs.groth16.exportSolidityCallData(
        proof,
        publicSignals
    );
    logStep("Calldata exportado", startMs);
    const argv = callData.replace(/[[\]\s\"]/g, "").split(",");

    const a = [argv[0], argv[1]];
    const b = [
        [argv[2], argv[3]],
        [argv[4], argv[5]],
    ];
    const c = [argv[6], argv[7]];
    const inputSignals = argv.slice(8);

    const output = {
        poseidon_root: toBytes32Hex(root),
        public_signals: {
            root: inputSignals[0],
            recipient: inputSignals[1],
            nonce: inputSignals[2],
        },
        proof: {
            a,
            b,
            c,
        },
    };

    fs.writeFileSync(outputPath, JSON.stringify(output, null, 2));
    logStep("Output salvo", startMs);
    process.exit(0);
}

main().catch((err) => {
    console.error(err.message || err);
    process.exit(1);
});
