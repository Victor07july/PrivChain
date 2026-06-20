pragma circom 2.1.6;

include "circomlib/circuits/poseidon.circom";

template TrajectoryMerkle512() {
    signal input lat[512];
    signal input lon[512];
    signal input recipient;
    signal input nonce;
    signal input root;
    signal dummy;

    component leafHasher[512];
    signal leaf[512];

    var i;
    for (i = 0; i < 512; i++) {
        leafHasher[i] = Poseidon(3);
        leafHasher[i].inputs[0] <== lat[i];
        leafHasher[i].inputs[1] <== lon[i];
        leafHasher[i].inputs[2] <== i;
        leaf[i] <== leafHasher[i].out;
    }

    component chunkHasher[64];
    signal chunk[64];
    var j;
    for (j = 0; j < 64; j++) {
        chunkHasher[j] = Poseidon(8);
        var k;
        for (k = 0; k < 8; k++) {
            chunkHasher[j].inputs[k] <== leaf[j * 8 + k];
        }
        chunk[j] <== chunkHasher[j].out;
    }

    component level1[32];
    signal l1[32];
    for (i = 0; i < 32; i++) {
        level1[i] = Poseidon(2);
        level1[i].inputs[0] <== chunk[2 * i];
        level1[i].inputs[1] <== chunk[2 * i + 1];
        l1[i] <== level1[i].out;
    }

    component level2[16];
    signal l2[16];
    for (i = 0; i < 16; i++) {
        level2[i] = Poseidon(2);
        level2[i].inputs[0] <== l1[2 * i];
        level2[i].inputs[1] <== l1[2 * i + 1];
        l2[i] <== level2[i].out;
    }

    component level3[8];
    signal l3[8];
    for (i = 0; i < 8; i++) {
        level3[i] = Poseidon(2);
        level3[i].inputs[0] <== l2[2 * i];
        level3[i].inputs[1] <== l2[2 * i + 1];
        l3[i] <== level3[i].out;
    }

    component level4[4];
    signal l4[4];
    for (i = 0; i < 4; i++) {
        level4[i] = Poseidon(2);
        level4[i].inputs[0] <== l3[2 * i];
        level4[i].inputs[1] <== l3[2 * i + 1];
        l4[i] <== level4[i].out;
    }

    component level5[2];
    signal l5[2];
    for (i = 0; i < 2; i++) {
        level5[i] = Poseidon(2);
        level5[i].inputs[0] <== l4[2 * i];
        level5[i].inputs[1] <== l4[2 * i + 1];
        l5[i] <== level5[i].out;
    }

    component level6[1];
    signal l6[1];
    level6[0] = Poseidon(2);
    level6[0].inputs[0] <== l5[0];
    level6[0].inputs[1] <== l5[1];
    l6[0] <== level6[0].out;

    root === l6[0];
    dummy <== recipient + nonce + root;
}

component main {public [root, recipient, nonce]} = TrajectoryMerkle512();
