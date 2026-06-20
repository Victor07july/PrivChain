// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import "@openzeppelin/contracts/token/ERC721/extensions/ERC721Enumerable.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

interface IZkVerifier {
    function verifyProof(
        uint256[2] calldata a,
        uint256[2][2] calldata b,
        uint256[2] calldata c,
        uint256[3] calldata input
    ) external view returns (bool);
}

/**
 * @title CarbonCreditNFT_E1
 * @dev Contrato adaptado do código Python - Cálculo E1 (emissões CO2)
 *
 * CÁLCULO E1 - META DE EMISSÃO CO2:
 * 1. Calcula Meta_CO2 baseado em consumo de combustível (gasolina/etanol)
 * 2. Compara com emissões reais para obter Diff (economia)
 * 3. Calcula valor monetário e1 usando preço do carbono europeu
 *
 * ESCALA DOS VALORES DE ENTRADA (conforme logica do test_adapted.py):
 * - distancias (highwayDistance, cityDistance): km * 1e6, sendo soma dos deltas incrementais do CSV
 * - realCO2Emissions: unidade bruta do CSV (ex: SUMO mg/passo) * 1e6, soma dos deltas incrementais
 *   IMPORTANTE: deve estar na MESMA unidade que a meta calculada (dist/consumo * fator_emissao).
 *   Se o CO2 do CSV ja estiver na mesma escala que o fator de emissao (2310), a comparacao e valida.
 * - carbonPricePerTon: BRL/tonelada * 1e6
 *
 * FLUXOS DISPONIVEIS:
 * - calculateAndPay(): calcula e1 e paga ETH imediatamente ao recipient (sem NFT, sem ZKP).
 *   Uso: envio direto, pseudonimo direto.
 * - calculateAndMintWithHash(): calcula e1, minta NFT para o recipient e registra hash SHA.
 *   O resgate ocorre via redeemWithZK() (requer poseidonRoot registrado pelo oraculo).
 *   Uso: cenario com oraculo (offset ou direto).
 *
 * CONSTANTES:
 * - EMISSAO_GASOLINA = 2.310 kg CO2/L (= 2310 na escala do CSV)
 * - EMISSAO_ETANOL = 1.510 kg CO2/L
 *
 * FÓRMULA:
 * Meta_CO2 = (dist_highway / consumo) * emissão + (dist_city / consumo) * emissão
 * Diff = max(0, Meta_CO2 - emissão_real)  [ambos na mesma unidade]
 * e1 = Diff * preço_carbono / 1_000_000 (valor em BRL * 1e6)
 */
contract CarbonCreditNFT_E1 is
    ERC721,
    ERC721Enumerable,
    ReentrancyGuard,
    Ownable
{
    // === ESTRUTURAS DE DADOS ===

    struct CalculationParams {
        uint256 highwayDistance; // Distância rodovia: km * 1e6 (soma dos deltas incrementais)
        uint256 cityDistance; // Distância cidade: km * 1e6 (soma dos deltas incrementais)
        uint256 ethanolPercent; // Percentual etanol (0-100) * 1e6
        uint256 roadGasoline; // Consumo rodovia gasolina (km/L) * 1e6
        uint256 roadEthanol; // Consumo rodovia etanol (km/L) * 1e6
        uint256 cityGasoline; // Consumo cidade gasolina (km/L) * 1e6
        uint256 cityEthanol; // Consumo cidade etanol (km/L) * 1e6
        uint256 realCO2Emissions; // Emissões reais: unidade CSV * 1e6 (soma dos deltas do CO2 bruto)
        uint256 carbonPricePerTon; // Preço carbono (BRL/tonelada) * 1e6
    }

    struct CalculationResult {
        uint256 tanqueGasoline; // Percentual gasolina no tanque
        uint256 parte1; // Emissões rodovia (unidade CSV) * 1e6
        uint256 parte2; // Emissões cidade (unidade CSV) * 1e6
        uint256 metaCO2; // Meta total CO2 (unidade CSV) * 1e6
        uint256 diff; // Economia CO2: max(0, meta - real) em unidade CSV * 1e6
        uint256 e1Value; // Valor monetário (BRL) * 1e6
        uint256 totalDistance; // Distância total percorrida
        bytes32 originalTrajectoryHash; // Hash da trajetoria original para auditoria
        bytes32 poseidonTrajectoryRoot; // Root Poseidon para prova ZK
    }

    // === EVENTOS ===
    event CarbonCreditCalculated(
        address indexed user,
        uint256 indexed tokenId,
        uint256 metaCO2,
        uint256 diff,
        uint256 e1Value,
        bytes32 originalTrajectoryHash,
        uint256 timestamp
    );

    event ZkRedeemed(
        address indexed recipient,
        bytes32 indexed poseidonRoot,
        uint256 tokenId,
        uint256 amount,
        uint256 timestamp
    );

    event DirectPayment(
        address indexed recipient,
        uint256 e1Value,
        bytes32 originalTrajectoryHash,
        uint256 timestamp
    );

    // === ESTADO DO CONTRATO ===
    uint256 private _nextTokenId = 1;
    mapping(uint256 => CalculationResult) public tokenCalculations;
    mapping(address => bool) public authorized;
    mapping(bytes32 => bool) public registeredTrajectoryHashes;
    mapping(bytes32 => bool) public registeredPoseidonRoots;
    mapping(bytes32 => bool) public usedZkNullifiers;
    mapping(bytes32 => uint256) public poseidonRootToTokenId;
    mapping(bytes32 => bool) public redeemedPoseidonRoots;
    IZkVerifier public zkVerifier;

    // === MODIFICADORES ===
    modifier onlyAuthorized() {
        require(
            authorized[msg.sender] || msg.sender == owner(),
            "Nao autorizado"
        );
        _;
    }

    // === CONSTRUTOR ===
    constructor() ERC721("CarbonCreditE1", "CCE1") {
        authorized[msg.sender] = true;
    }

    function setZkVerifier(address verifier) external onlyOwner {
        zkVerifier = IZkVerifier(verifier);
    }

    // === FUNÇÃO PRINCIPAL: CALCULAR E1 E CRIAR NFT ===
    function calculateAndMint(
        CalculationParams memory params,
        address recipient
    )
        external
        onlyAuthorized
        nonReentrant
        returns (uint256 tokenId, uint256 e1Value)
    {
        return _calculateAndMint(params, recipient, bytes32(0));
    }

    function calculateAndMintWithHash(
        CalculationParams memory params,
        address recipient,
        bytes32 originalTrajectoryHash
    )
        external
        onlyAuthorized
        nonReentrant
        returns (uint256 tokenId, uint256 e1Value)
    {
        return _calculateAndMint(params, recipient, originalTrajectoryHash);
    }

    function _calculateAndMint(
        CalculationParams memory params,
        address recipient,
        bytes32 originalTrajectoryHash
    ) internal returns (uint256 tokenId, uint256 e1Value) {
        // Validações básicas
        require(params.roadGasoline > 0, "Road gasoline deve ser > 0");
        require(params.cityGasoline > 0, "City gasoline deve ser > 0");
        require(params.carbonPricePerTon > 0, "Carbon price deve ser > 0");

        // Executar cálculos
        CalculationResult memory result = _performCalculations(params);

        // Criar NFT
        tokenId = _nextTokenId++;
        _safeMint(recipient, tokenId);

        // Armazenar resultado
        result.originalTrajectoryHash = originalTrajectoryHash;
        tokenCalculations[tokenId] = result;
        if (originalTrajectoryHash != bytes32(0)) {
            registeredTrajectoryHashes[originalTrajectoryHash] = true;
        }
        e1Value = result.e1Value;

        // Emitir evento
        emit CarbonCreditCalculated(
            recipient,
            tokenId,
            result.metaCO2,
            result.diff,
            e1Value,
            originalTrajectoryHash,
            block.timestamp
        );

        return (tokenId, e1Value);
    }

    /**
     * @notice Calcula o e1Value e paga ETH imediatamente ao recipient.
     * Nao minta NFT — o credito e liquidado na mesma transacao.
     * Uso: envio direto (sem oraculo, sem ZKP).
     * Requer que o contrato tenha saldo ETH suficiente.
     */
    function calculateAndPay(
        CalculationParams memory params,
        address payable recipient,
        bytes32 originalTrajectoryHash
    )
        external
        onlyAuthorized
        nonReentrant
        returns (uint256 e1Value)
    {
        require(params.roadGasoline > 0, "Road gasoline deve ser > 0");
        require(params.cityGasoline > 0, "City gasoline deve ser > 0");
        require(params.carbonPricePerTon > 0, "Carbon price deve ser > 0");
        require(recipient != address(0), "Recipient invalido");

        CalculationResult memory result = _performCalculations(params);
        e1Value = result.e1Value;
        require(e1Value > 0, "e1Value calculado e zero");
        require(
            address(this).balance >= e1Value,
            "Saldo insuficiente no contrato"
        );

        if (originalTrajectoryHash != bytes32(0)) {
            registeredTrajectoryHashes[originalTrajectoryHash] = true;
        }

        (bool sent, ) = recipient.call{value: e1Value}("");
        require(sent, "Falha ao transferir ETH");

        emit DirectPayment(
            recipient,
            e1Value,
            originalTrajectoryHash,
            block.timestamp
        );

        return e1Value;
    }

    /**
     * @notice Calcula e1Value via ZKP, minta NFT com poseidonRoot registrado
     * e armazena o valor para resgate posterior via redeemWithZK.
     * Uso: cenario com oraculo (com ou sem offset).
     */
    function calculateAndMintWithZK(
        CalculationParams memory params,
        address recipient,
        bytes32 originalTrajectoryHash,
        bytes32 poseidonRoot,
        uint256 nonce,
        uint256[2] calldata proofA,
        uint256[2][2] calldata proofB,
        uint256[2] calldata proofC
    )
        external
        onlyAuthorized
        nonReentrant
        returns (uint256 tokenId, uint256 e1Value)
    {
        require(poseidonRoot != bytes32(0), "poseidonRoot invalido");
        require(
            address(zkVerifier) != address(0),
            "ZK verifier nao configurado"
        );
        require(
            !registeredPoseidonRoots[poseidonRoot],
            "poseidonRoot ja registrado"
        );
        require(params.roadGasoline > 0, "Road gasoline deve ser > 0");
        require(params.cityGasoline > 0, "City gasoline deve ser > 0");
        require(params.carbonPricePerTon > 0, "Carbon price deve ser > 0");

        bytes32 nullifier = keccak256(
            abi.encodePacked(poseidonRoot, recipient, nonce)
        );
        require(!usedZkNullifiers[nullifier], "Proof ja utilizado");

        bool ok = zkVerifier.verifyProof(
            proofA,
            proofB,
            proofC,
            [uint256(uint160(recipient)), nonce, uint256(poseidonRoot)]
        );
        require(ok, "Proof ZK invalido");

        CalculationResult memory result = _performCalculations(params);
        e1Value = result.e1Value;
        require(e1Value > 0, "e1Value calculado e zero");

        usedZkNullifiers[nullifier] = true;

        tokenId = _nextTokenId++;
        _safeMint(recipient, tokenId);

        result.originalTrajectoryHash = originalTrajectoryHash;
        result.poseidonTrajectoryRoot = poseidonRoot;

        tokenCalculations[tokenId] = result;
        if (originalTrajectoryHash != bytes32(0)) {
            registeredTrajectoryHashes[originalTrajectoryHash] = true;
        }
        registeredPoseidonRoots[poseidonRoot] = true;
        poseidonRootToTokenId[poseidonRoot] = tokenId;

        emit CarbonCreditCalculated(
            recipient,
            tokenId,
            result.metaCO2,
            result.diff,
            e1Value,
            originalTrajectoryHash,
            block.timestamp
        );

        return (tokenId, e1Value);
    }

    // === CÁLCULOS INTERNOS (BASEADO NO CÓDIGO PYTHON / test_adapted.py) ===
    //
    // IMPORTANTE: realCO2Emissions deve estar na mesma escala que a meta calculada.
    // A meta e calculada como (distancia_km / consumo_kmL) * 2310, portanto
    // realCO2Emissions deve ser a soma dos deltas do CO2 bruto do CSV na mesma escala.
    // Ambos sao escalados por 1e6 para preservar precisao inteira.
    //
    // Formula de monetizacao:
    //   e1_micro = (diff_micro * price_micro) / 1e12
    //   onde e1_micro = e1_brl * 1e6  e  e1_brl = diff * price / 1_000_000
    function _performCalculations(
        CalculationParams memory params
    ) internal pure returns (CalculationResult memory result) {
        // Fator de emissao: 2310 unidades CSV por L de gasolina (mesmo fator do test_adapted.py)
        uint256 EMISSAO_GASOLINA = 2310 * 1e6; // unidade_csv * 1e6
        uint256 EMISSAO_ETANOL = 1510 * 1e6;   // unidade_csv * 1e6

        // Tanque 100% gasolina (etanol nao considerado neste fluxo)
        result.tanqueGasoline = 100 * 1e6;
        uint256 p_gas = result.tanqueGasoline;

        // Parte 1: emissoes rodovia
        // meta_highway = (highwayDistance_km / roadGasoline_kmL) * 2310
        // Em micros: (highwayDistance_micro * EMISSAO_micro * p_gas_micro) / (roadGasoline_micro * 100 * 1e6)
        uint256 parte_1_1 = 0;
        if (params.roadGasoline > 0) {
            parte_1_1 =
                (params.highwayDistance * EMISSAO_GASOLINA * p_gas) /
                (params.roadGasoline * 100 * 1e6);
        }
        result.parte1 = parte_1_1;

        // Parte 2: emissoes cidade
        uint256 parte_2_1 = 0;
        if (params.cityGasoline > 0) {
            parte_2_1 =
                (params.cityDistance * EMISSAO_GASOLINA * p_gas) /
                (params.cityGasoline * 100 * 1e6);
        }
        result.parte2 = parte_2_1;

        // Meta_CO2 total (unidade CSV * 1e6)
        result.metaCO2 = result.parte1 + result.parte2;

        // Diff = max(0, meta - real)  [test_adapted.py: Diff = Meta_CO2 - CO2_delta, clipped >= 0]
        if (result.metaCO2 >= params.realCO2Emissions) {
            result.diff = result.metaCO2 - params.realCO2Emissions;
        } else {
            result.diff = 0;
        }

        // e1 (BRL * 1e6):
        //   e1_brl = diff * carbonPrice / 1_000_000  [test_adapted.py]
        //   e1_micro = e1_brl * 1e6 = (diff_micro * price_micro) / 1e12
        result.e1Value =
            (result.diff * params.carbonPricePerTon) /
            (1_000_000 * 1e6);

        result.totalDistance = params.highwayDistance + params.cityDistance;

        return result;
    }

    // === FUNÇÕES DE VISUALIZAÇÃO ===
    function getCalculationDetails(
        uint256 tokenId
    ) external view returns (CalculationResult memory) {
        require(_ownerOf(tokenId) != address(0), "Token nao existe");
        return tokenCalculations[tokenId];
    }

    function getBatchCalculations(
        uint256[] memory tokenIds
    ) external view returns (CalculationResult[] memory) {
        CalculationResult[] memory results = new CalculationResult[](
            tokenIds.length
        );
        for (uint256 i = 0; i < tokenIds.length; i++) {
            require(_ownerOf(tokenIds[i]) != address(0), "Token nao existe");
            results[i] = tokenCalculations[tokenIds[i]];
        }
        return results;
    }

    function getOriginalTrajectoryHash(
        uint256 tokenId
    ) external view returns (bytes32) {
        require(_ownerOf(tokenId) != address(0), "Token nao existe");
        return tokenCalculations[tokenId].originalTrajectoryHash;
    }

    function getPoseidonTrajectoryRoot(
        uint256 tokenId
    ) external view returns (bytes32) {
        require(_ownerOf(tokenId) != address(0), "Token nao existe");
        return tokenCalculations[tokenId].poseidonTrajectoryRoot;
    }

    function verifyOriginalTrajectoryHash(
        uint256 tokenId,
        bytes32 providedHash
    ) external view returns (bool) {
        require(_ownerOf(tokenId) != address(0), "Token nao existe");
        return
            tokenCalculations[tokenId].originalTrajectoryHash == providedHash;
    }

    function verifyPoseidonTrajectoryRoot(
        uint256 tokenId,
        bytes32 providedRoot
    ) external view returns (bool) {
        require(_ownerOf(tokenId) != address(0), "Token nao existe");
        return
            tokenCalculations[tokenId].poseidonTrajectoryRoot == providedRoot;
    }

    function isTrajectoryHashRegistered(
        bytes32 providedHash
    ) external view returns (bool) {
        return registeredTrajectoryHashes[providedHash];
    }

    function isPoseidonRootRegistered(
        bytes32 providedRoot
    ) external view returns (bool) {
        return registeredPoseidonRoots[providedRoot];
    }

    function redeemWithZK(
        bytes32 poseidonRoot,
        uint256 nonce,
        uint256[2] calldata proofA,
        uint256[2][2] calldata proofB,
        uint256[2] calldata proofC
    ) external nonReentrant returns (uint256 tokenId, uint256 amount) {
        require(poseidonRoot != bytes32(0), "poseidonRoot invalido");
        require(
            registeredPoseidonRoots[poseidonRoot],
            "poseidonRoot nao registrado"
        );
        require(
            !redeemedPoseidonRoots[poseidonRoot],
            "poseidonRoot ja resgatado"
        );
        require(
            address(zkVerifier) != address(0),
            "ZK verifier nao configurado"
        );

        tokenId = poseidonRootToTokenId[poseidonRoot];
        require(tokenId != 0, "tokenId nao encontrado");

        bytes32 nullifier = keccak256(
            abi.encodePacked(poseidonRoot, msg.sender, nonce)
        );
        require(!usedZkNullifiers[nullifier], "Proof ja utilizado");

        bool ok = zkVerifier.verifyProof(
            proofA,
            proofB,
            proofC,
            [uint256(uint160(msg.sender)), nonce, uint256(poseidonRoot)]
        );
        require(ok, "Proof ZK invalido");

        usedZkNullifiers[nullifier] = true;
        redeemedPoseidonRoots[poseidonRoot] = true;

        amount = tokenCalculations[tokenId].e1Value;
        require(amount > 0, "Valor de resgate invalido");
        require(
            address(this).balance >= amount,
            "Saldo insuficiente no contrato"
        );

        _burn(tokenId);

        (bool sent, ) = msg.sender.call{value: amount}("");
        require(sent, "Falha ao transferir");

        emit ZkRedeemed(
            msg.sender,
            poseidonRoot,
            tokenId,
            amount,
            block.timestamp
        );
        return (tokenId, amount);
    }

    // === FUNÇÕES ADMINISTRATIVAS ===
    function setAuthorized(address user, bool status) external onlyOwner {
        authorized[user] = status;
    }

    function nextTokenId() external view returns (uint256) {
        return _nextTokenId;
    }

    // === FUNÇÕES REQUERIDAS PELO ERC721Enumerable ===
    function _beforeTokenTransfer(
        address from,
        address to,
        uint256 tokenId,
        uint256 batchSize
    ) internal override(ERC721, ERC721Enumerable) {
        super._beforeTokenTransfer(from, to, tokenId, batchSize);
    }

    function supportsInterface(
        bytes4 interfaceId
    ) public view override(ERC721, ERC721Enumerable) returns (bool) {
        return super.supportsInterface(interfaceId);
    }

    // === FUNÇÃO PARA RECEBER ETH ===
    receive() external payable {}

    function withdraw() external onlyOwner {
        payable(msg.sender).transfer(address(this).balance);
    }

    function getContractBalance() external view returns (uint256) {
        return address(this).balance;
    }
}
