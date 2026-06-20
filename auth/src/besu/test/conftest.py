"""
Fixtures compartilhadas para testes do módulo besu
"""
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_web3():
    """
    Mock básico do Web3 conectado
    """
    mock_w3 = AsyncMock()
    mock_w3.is_connected.return_value = True
    return mock_w3


@pytest.fixture
def mock_web3_disconnected():
    """
    Mock do Web3 desconectado
    """
    mock_w3 = AsyncMock()
    mock_w3.is_connected.return_value = False
    return mock_w3


@pytest.fixture
def valid_signed_transaction():
    """Transação assinada válida em formato hexadecimal"""
    # Uma transação RLP-encoded válida (simplificada para testes)
    # Esta é uma transação real serializada que passa na validação bytes.fromhex()
    return "0xf86c808504a817c800825208949876543210abcdef0123456789abcdef0123456789880de0b6b3a764000080820a96a01234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdefa01234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"


@pytest.fixture
def mock_tx_hash():
    """
    Mock de transaction hash
    """
    mock_hash = MagicMock()
    mock_hash.hex.return_value = '0xabc123def456...'
    return mock_hash


@pytest.fixture
def mock_success_receipt():
    """
    Mock de receipt bem-sucedido (status=1)
    """
    mock_receipt = MagicMock()
    mock_receipt.status = 1
    mock_receipt.contractAddress = '0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb'
    mock_receipt.gasUsed = 180910
    return mock_receipt


@pytest.fixture
def mock_failed_receipt():
    """
    Mock de receipt com falha (status=0)
    """
    mock_receipt = MagicMock()
    mock_receipt.status = 0
    mock_receipt.gasUsed = 100000
    return mock_receipt


@pytest.fixture
def mock_transaction():
    """
    Mock de transaction object
    """
    mock_tx = MagicMock()
    mock_tx.gas = 3000000
    return mock_tx


@pytest.fixture
def mock_compilation_success():
    """
    Mock de ContractCompilationResponse bem-sucedida
    """
    from src.besu.schemas import ContractCompilationResponse
    return ContractCompilationResponse(
        success=True,
        abi=[{"name": "value", "type": "function"}],
        bytecode="0x608060405234801561001057600080fd5b50"
    )


@pytest.fixture
def mock_compilation_failed():
    """
    Mock de ContractCompilationResponse com falha
    """
    from src.besu.schemas import ContractCompilationResponse
    return ContractCompilationResponse(
        success=False,
        error_message="Erro de compilação"
    )


@pytest.fixture
def valid_deployer_address():
    """Endereço Ethereum válido"""
    return "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb"


@pytest.fixture
def invalid_deployer_address():
    """Endereço Ethereum inválido"""
    return "not-an-address"