"""
Testes unitários para src.besu.services

Testa os cenários de erro e sucesso das funções:
- broadcast_signed_transaction
- compile_solidity_contract
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from unittest.mock import PropertyMock
from src.besu.services import broadcast_signed_transaction, compile_solidity_contract
from src.besu.schemas import SignedTransactionResponse, ContractCompilationResponse


@pytest.mark.asyncio
class TestBroadcastSignedTransaction:
    """
    Testes para a função broadcast_signed_transaction
    Cobre todos os cenários de erro tratados no código
    """
    
    async def test_success_contract_deployment(
        self,
        mock_web3,
        valid_signed_transaction,
        mock_tx_hash,
        mock_success_receipt
    ):
        """
        Cenário: Deploy de contrato bem-sucedido
        Resultado esperado: success=True, contract_address presente
        """
        # Arrange
        mock_web3.eth.send_raw_transaction.return_value = mock_tx_hash
        mock_web3.eth.wait_for_transaction_receipt.return_value = mock_success_receipt
        
        # Act
        result = await broadcast_signed_transaction(mock_web3, valid_signed_transaction)
        
        # Assert
        assert result.success == True
        assert result.contract_address == '0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb'
        assert result.gas_used == 180910
        assert result.error_message is None
        assert result.transaction_hash == '0xabc123def456...'
    
    async def test_besu_not_connected(self, mock_web3_disconnected, valid_signed_transaction):
        """
        Cenário: Besu não está conectado
        Resultado esperado: success=False, erro de conexão
        """
        # Act
        result = await broadcast_signed_transaction(
            mock_web3_disconnected,
            valid_signed_transaction
        )
        
        # Assert
        assert result.success == False
        assert "conectar" in result.error_message.lower()
        assert "besu" in result.error_message.lower()
    
    async def test_empty_signed_transaction(self, mock_web3):
        """
        Cenário: Transação assinada vazia
        Resultado esperado: success=False, erro de validação
        """
        # Act
        result = await broadcast_signed_transaction(mock_web3, "")
        
        # Assert
        assert result.success == False
        assert "não fornecida" in result.error_message.lower()
    
    async def test_invalid_hex_format(self, mock_web3):
        """
        Cenário: Transação com formato hexadecimal inválido
        Resultado esperado: success=False, erro de formato
        """
        # Act
        result = await broadcast_signed_transaction(mock_web3, "not-a-valid-hex-string")
        
        # Assert
        assert result.success == False
        assert "hexadecimal" in result.error_message.lower()
    
    async def test_gas_error_intrinsic_gas_exceeds_limit(
        self,
        mock_web3,
        valid_signed_transaction
    ):
        """
        Cenário: Gas limit definido é menor que o gas intrínseco necessário
        Erro: "Intrinsic gas exceeds gas limit"
        Resultado esperado: success=False, mensagem específica de gas
        """
        # Arrange
        mock_web3.eth.send_raw_transaction.side_effect = Exception(
            "{'code': -32003, 'message': 'Intrinsic gas exceeds gas limit'}"
        )
        
        # Act
        result = await broadcast_signed_transaction(mock_web3, valid_signed_transaction)
        
        # Assert
        assert result.success == False
        assert "gas" in result.error_message.lower()
        assert "gas_limit" in result.error_message.lower()
    
    async def test_gas_error_out_of_gas(self, mock_web3, valid_signed_transaction):
        """
        Cenário: Gas insuficiente durante execução
        Erro: "out of gas"
        Resultado esperado: success=False, mensagem de gas
        """
        # Arrange
        mock_web3.eth.send_raw_transaction.side_effect = ValueError(
            "out of gas: required 5000000, but only 3000000 available"
        )
        
        # Act
        result = await broadcast_signed_transaction(mock_web3, valid_signed_transaction)
        
        # Assert
        assert result.success == False
        assert "gas" in result.error_message.lower()
    
    async def test_nonce_error_too_low(self, mock_web3, valid_signed_transaction):
        """
        Cenário: Nonce muito baixo (transação já foi usada)
        Erro: "nonce too low"
        Resultado esperado: success=False, mensagem de nonce
        """
        # Arrange
        mock_web3.eth.send_raw_transaction.side_effect = ValueError(
            "nonce too low: address 0x123..., tx: 10 state: 11"
        )
        
        # Act
        result = await broadcast_signed_transaction(mock_web3, valid_signed_transaction)
        
        # Assert
        assert result.success == False
        assert "nonce" in result.error_message.lower()
        assert "correto" in result.error_message.lower()
    
    async def test_nonce_error_too_high(self, mock_web3, valid_signed_transaction):
        """
        Cenário: Nonce muito alto (há gap nas transações)
        Erro: "nonce too high"
        Resultado esperado: success=False, mensagem de nonce
        """
        # Arrange
        mock_web3.eth.send_raw_transaction.side_effect = ValueError(
            "nonce too high: address 0x123..., tx: 15 state: 10"
        )
        
        # Act
        result = await broadcast_signed_transaction(mock_web3, valid_signed_transaction)
        
        # Assert
        assert result.success == False
        assert "nonce" in result.error_message.lower()
    
    async def test_transaction_timeout(
        self,
        mock_web3,
        valid_signed_transaction,
        mock_tx_hash
    ):
        """
        Cenário: Transação enviada mas timeout ao aguardar confirmação
        Resultado esperado: success=False, mas transaction_hash presente
        """
        # Arrange
        mock_web3.eth.send_raw_transaction.return_value = mock_tx_hash
        mock_web3.eth.wait_for_transaction_receipt.side_effect = TimeoutError(
            "Timeout waiting for transaction receipt"
        )
        
        # Act
        result = await broadcast_signed_transaction(mock_web3, valid_signed_transaction)
        
        # Assert
        assert result.success == False
        assert "timeout" in result.error_message.lower()
        assert result.transaction_hash == '0xabc123def456...'
    
    async def test_transaction_reverted_out_of_gas(
        self,
        mock_web3,
        valid_signed_transaction,
        mock_tx_hash,
        mock_failed_receipt,
        mock_transaction
    ):
        """
        Cenário: Transação revertida por falta de gas (usou 95%+ do limit)
        Resultado esperado: success=False, mensagem "Out of Gas"
        """
        # Arrange
        mock_failed_receipt.gasUsed = 2850000  # 95% de 3M
        mock_web3.eth.send_raw_transaction.return_value = mock_tx_hash
        mock_web3.eth.wait_for_transaction_receipt.return_value = mock_failed_receipt
        mock_web3.eth.get_transaction.return_value = mock_transaction
        
        # Act
        result = await broadcast_signed_transaction(mock_web3, valid_signed_transaction)
        
        # Assert
        assert result.success == False
        assert "out of gas" in result.error_message.lower()
        assert "2850000/3000000" in result.error_message
        assert "4500000" in result.error_message  # Sugestão de 1.5x
    
    async def test_transaction_reverted_contract_error(
        self,
        mock_web3,
        valid_signed_transaction,
        mock_tx_hash,
        mock_failed_receipt,
        mock_transaction
    ):
        """
        Cenário: Transação revertida por erro no construtor (não é falta de gas)
        Resultado esperado: success=False, mensagem sobre erro no construtor
        """
        # Arrange
        mock_failed_receipt.gasUsed = 50000  # Muito menos que o limit
        mock_web3.eth.send_raw_transaction.return_value = mock_tx_hash
        mock_web3.eth.wait_for_transaction_receipt.return_value = mock_failed_receipt
        mock_web3.eth.get_transaction.return_value = mock_transaction
        
        # Act
        result = await broadcast_signed_transaction(mock_web3, valid_signed_transaction)
        
        # Assert
        assert result.success == False
        assert "revertida" in result.error_message.lower()
        assert "construtor" in result.error_message.lower()
        assert "50000/3000000" in result.error_message
    
    async def test_transaction_reverted_cannot_get_tx_details(
        self,
        mock_web3,
        valid_signed_transaction,
        mock_tx_hash,
        mock_failed_receipt
    ):
        """
        Cenário: Transação revertida mas não consegue obter detalhes da TX
        Resultado esperado: success=False, mensagem genérica
        """
        # Arrange
        mock_failed_receipt.gasUsed = 100000
        mock_web3.eth.send_raw_transaction.return_value = mock_tx_hash
        mock_web3.eth.wait_for_transaction_receipt.return_value = mock_failed_receipt
        mock_web3.eth.get_transaction.side_effect = Exception("Cannot get transaction")
        
        # Act
        result = await broadcast_signed_transaction(mock_web3, valid_signed_transaction)
        
        # Assert
        assert result.success == False
        assert "revertida" in result.error_message.lower()
        assert "status=0" in result.error_message.lower()
        assert "100000" in result.error_message
    
    async def test_generic_error_on_send(self, mock_web3, valid_signed_transaction):
        """
        Cenário: Erro genérico ao enviar transação (não é gas, nonce ou funds)
        Resultado esperado: success=False, mensagem genérica
        """
        # Arrange
        mock_web3.eth.send_raw_transaction.side_effect = Exception(
            "Unknown network error"
        )
        
        # Act
        result = await broadcast_signed_transaction(mock_web3, valid_signed_transaction)
        
        # Assert
        assert result.success == False
        assert "erro ao enviar transação" in result.error_message.lower()
    
    async def test_unexpected_exception_in_function(
        self,
        mock_web3,
        valid_signed_transaction
    ):
        """
        Cenário: Exceção inesperada em qualquer parte da função
        Resultado esperado: success=False, erro interno
        """
        # Arrange
        mock_web3.is_connected.side_effect = Exception("Unexpected error")
        
        # Act
        result = await broadcast_signed_transaction(mock_web3, valid_signed_transaction)
        
        # Assert
        assert result.success == False
        assert "erro interno" in result.error_message.lower()


@pytest.mark.asyncio
class TestCompileSolidityContract:
    """
    Testes para a função compile_solidity_contract
    Cobre cenários básicos de compilação
    """
    
    async def test_invalid_file_extension(self):
        """
        Cenário: Arquivo com extensão inválida (.txt, .js, etc)
        Resultado esperado: success=False, erro de extensão
        """
        # Arrange
        mock_file = MagicMock()
        mock_file.filename = "contract.txt"
        
        # Act
        result = await compile_solidity_contract(mock_file)
        
        # Assert
        assert result.success == False
        assert ".sol" in result.error_message
    
    @patch('solcx.compile_source')
    @patch('solcx.install_solc')
    @patch('solcx.set_solc_version')
    async def test_compilation_success(
        self,
        mock_set_version,
        mock_install,
        mock_compile
    ):
        """
        Cenário: Compilação bem-sucedida de contrato simples
        Resultado esperado: success=True, abi e bytecode presentes
        """
        # Arrange
        mock_file = MagicMock()
        mock_file.filename = "SimpleStorage.sol"
        mock_file.read = AsyncMock(return_value=b'''
            pragma solidity ^0.8.19;
            contract SimpleStorage {
                uint256 public value;
            }
        ''')
        
        mock_compile.return_value = {
            '<stdin>:SimpleStorage': {
                'abi': [{'name': 'value', 'type': 'function'}],
                'bin': '608060405234801561001057600080fd5b50'
            }
        }
        
        # Act
        result = await compile_solidity_contract(mock_file)
        
        # Assert
        assert result.success == True
        assert result.abi is not None
        assert result.bytecode is not None
        assert len(result.bytecode) > 0
    
    @patch('solcx.compile_source')
    @patch('solcx.install_solc')
    @patch('solcx.set_solc_version')
    async def test_compilation_syntax_error(
        self,
        mock_set_version,
        mock_install,
        mock_compile
    ):
        """
        Cenário: Erro de sintaxe no contrato Solidity
        Resultado esperado: success=False, mensagem de syntax error
        """
        # Arrange
        mock_file = MagicMock()
        mock_file.filename = "BadContract.sol"
        mock_file.read = AsyncMock(return_value=b'pragma solidity ^0.8.19; contract {')
        
        mock_compile.side_effect = Exception(
            "SyntaxError: Expected identifier but got '{'"
        )
        
        # Act
        result = await compile_solidity_contract(mock_file)
        
        # Assert
        assert result.success == False
        assert "sintaxe" in result.error_message.lower()
    
    @patch('solcx.compile_source')
    @patch('solcx.install_solc')
    @patch('solcx.set_solc_version')
    async def test_compilation_type_error(
        self,
        mock_set_version,
        mock_install,
        mock_compile
    ):
        """
        Cenário: Erro de tipo no contrato Solidity
        Resultado esperado: success=False, mensagem de type error
        """
        # Arrange
        mock_file = MagicMock()
        mock_file.filename = "TypeErrorContract.sol"
        mock_file.read = AsyncMock(return_value=b'''
            pragma solidity ^0.8.19;
            contract Test {
                function test() public {
                    uint256 x = "string";
                }
            }
        ''')
        
        mock_compile.side_effect = Exception(
            "TypeError: Type string is not implicitly convertible to uint256"
        )
        
        # Act
        result = await compile_solidity_contract(mock_file)
        
        # Assert
        assert result.success == False
        assert "tipo" in result.error_message.lower()


@pytest.mark.asyncio
class TestPrepareDeploymentTransaction:
    """
    Testes para a função prepare_deployment_transaction
    Cobre todos os cenários de preparação de transação de deployment
    """
    
    async def test_success_with_constructor_params(
        self,
        mock_web3,
        mock_compilation_success,
        valid_deployer_address
    ):
        """
        Cenário: Preparação bem-sucedida com parâmetros no construtor
        Resultado esperado: success=True, transaction com todos os campos
        """
        from src.besu.services import prepare_deployment_transaction
        
        # Arrange
        # to_checksum_address é síncrono no Web3
        mock_web3.to_checksum_address = MagicMock(return_value=valid_deployer_address)
        
        # Configurar mock_web3.eth como MagicMock para evitar problemas com AsyncMock
        mock_eth = MagicMock()
        mock_eth.get_transaction_count = AsyncMock(return_value=5)
        # gas_price e chain_id são propriedades que retornam corrotinas
        type(mock_eth).gas_price = PropertyMock(return_value=AsyncMock(return_value=1000000000)())
        type(mock_eth).chain_id = PropertyMock(return_value=AsyncMock(return_value=1337)())
        
        # Mock do contrato e construtor (MUST be MagicMock, not AsyncMock)
        mock_contract = MagicMock()
        mock_constructor = MagicMock()
        mock_constructor.data_in_transaction = "0x608060405234801561001057600080fd5b50"
        mock_contract.constructor.return_value = mock_constructor
        mock_eth.contract = MagicMock(return_value=mock_contract)
        
        mock_web3.eth = mock_eth
        
        constructor_params = '[42, "test"]'
        gas_limit = 3000000
        
        # Act
        result = await prepare_deployment_transaction(
            w3=mock_web3,
            compilation_result=mock_compilation_success,
            deployer_address=valid_deployer_address,
            constructor_params_json=constructor_params,
            gas_limit=gas_limit
        )
        
        # Assert
        assert result.success == True
        assert result.transaction is not None
        assert result.transaction['from'] == valid_deployer_address
        assert result.transaction['nonce'] == 5
        assert result.transaction['gas'] == 3000000
        assert result.transaction['gasPrice'] == 1000000000
        assert result.transaction['chainId'] == 1337
        assert result.transaction['value'] == 0
        assert 'data' in result.transaction
    
    async def test_success_without_constructor_params(
        self,
        mock_web3,
        mock_compilation_success,
        valid_deployer_address
    ):
        """
        Cenário: Preparação bem-sucedida sem parâmetros no construtor
        Resultado esperado: success=True, data é apenas o bytecode
        """
        from src.besu.services import prepare_deployment_transaction
        
        # Arrange
        mock_web3.to_checksum_address = MagicMock(return_value=valid_deployer_address)
        
        mock_eth = MagicMock()
        mock_eth.get_transaction_count = AsyncMock(return_value=0)
        type(mock_eth).gas_price = PropertyMock(return_value=AsyncMock(return_value=2000000000)())
        type(mock_eth).chain_id = PropertyMock(return_value=AsyncMock(return_value=1337)())
        
        mock_contract = MagicMock()
        mock_eth.contract = MagicMock(return_value=mock_contract)
        
        mock_web3.eth = mock_eth
        
        constructor_params = '[]'
        gas_limit = 5000000
        
        # Act
        result = await prepare_deployment_transaction(
            w3=mock_web3,
            compilation_result=mock_compilation_success,
            deployer_address=valid_deployer_address,
            constructor_params_json=constructor_params,
            gas_limit=gas_limit
        )
        
        # Assert
        assert result.success == True
        assert result.transaction is not None
        assert result.transaction['nonce'] == 0
        assert result.transaction['gas'] == 5000000
        # Data deve ser o bytecode quando não há parâmetros
        assert result.transaction['data'].startswith('0x')
    
    async def test_compilation_failed(
        self,
        mock_web3,
        mock_compilation_failed,
        valid_deployer_address
    ):
        """
        Cenário: Compilação falhou antes de preparar transação
        Resultado esperado: Retorna o mesmo objeto de erro da compilação
        """
        from src.besu.services import prepare_deployment_transaction
        
        # Act
        result = await prepare_deployment_transaction(
            w3=mock_web3,
            compilation_result=mock_compilation_failed,
            deployer_address=valid_deployer_address,
            constructor_params_json='[]',
            gas_limit=3000000
        )
        
        # Assert
        assert result.success == False
        assert result.error_message == "Erro de compilação"
    
    async def test_invalid_json_constructor_params(
        self,
        mock_web3,
        mock_compilation_success,
        valid_deployer_address
    ):
        """
        Cenário: constructor_params não é JSON válido
        Resultado esperado: success=False, erro de parsing
        """
        from src.besu.services import prepare_deployment_transaction
        
        # Act
        result = await prepare_deployment_transaction(
            w3=mock_web3,
            compilation_result=mock_compilation_success,
            deployer_address=valid_deployer_address,
            constructor_params_json='not-a-json',
            gas_limit=3000000
        )
        
        # Assert
        assert result.success == False
        assert "parsear constructor_params" in result.error_message
    
    async def test_constructor_params_not_array(
        self,
        mock_web3,
        mock_compilation_success,
        valid_deployer_address
    ):
        """
        Cenário: constructor_params é JSON válido mas não é um array
        Resultado esperado: success=False, erro de tipo
        """
        from src.besu.services import prepare_deployment_transaction
        
        # Act
        result = await prepare_deployment_transaction(
            w3=mock_web3,
            compilation_result=mock_compilation_success,
            deployer_address=valid_deployer_address,
            constructor_params_json='{"key": "value"}',  # Objeto, não array
            gas_limit=3000000
        )
        
        # Assert
        assert result.success == False
        assert "array JSON" in result.error_message
    
    async def test_invalid_deployer_address_no_0x(
        self,
        mock_web3,
        mock_compilation_success
    ):
        """
        Cenário: deployer_address sem prefixo 0x
        Resultado esperado: success=False, erro de validação
        """
        from src.besu.services import prepare_deployment_transaction
        
        # Act
        result = await prepare_deployment_transaction(
            w3=mock_web3,
            compilation_result=mock_compilation_success,
            deployer_address="742d35Cc6634C0532925a3b844Bc9e7595f0bEb",  # Sem 0x
            constructor_params_json='[]',
            gas_limit=3000000
        )
        
        # Assert
        assert result.success == False
        assert "0x" in result.error_message
    
    async def test_invalid_deployer_address_format(
        self,
        mock_web3,
        mock_compilation_success,
        invalid_deployer_address
    ):
        """
        Cenário: deployer_address com formato inválido
        Resultado esperado: success=False, erro ao converter para checksum
        """
        from src.besu.services import prepare_deployment_transaction
        
        # Arrange
        mock_web3.to_checksum_address = MagicMock(side_effect=Exception("Invalid address"))
        
        # Act
        result = await prepare_deployment_transaction(
            w3=mock_web3,
            compilation_result=mock_compilation_success,
            deployer_address="0xinvalid",
            constructor_params_json='[]',
            gas_limit=3000000
        )
        
        # Assert
        assert result.success == False
        assert "inválido" in result.error_message.lower()
    
    async def test_empty_deployer_address(
        self,
        mock_web3,
        mock_compilation_success
    ):
        """
        Cenário: deployer_address vazio
        Resultado esperado: success=False, erro de validação
        """
        from src.besu.services import prepare_deployment_transaction
        
        # Act
        result = await prepare_deployment_transaction(
            w3=mock_web3,
            compilation_result=mock_compilation_success,
            deployer_address="",
            constructor_params_json='[]',
            gas_limit=3000000
        )
        
        # Assert
        assert result.success == False
        assert "inválido" in result.error_message
    
    async def test_error_encoding_constructor(
        self,
        mock_web3,
        mock_compilation_success,
        valid_deployer_address
    ):
        """
        Cenário: Erro ao encodar construtor (params incompatíveis com ABI)
        Resultado esperado: success=False, erro ao preparar transação
        """
        from src.besu.services import prepare_deployment_transaction
        
        # Arrange
        mock_web3.to_checksum_address = MagicMock(return_value=valid_deployer_address)
        mock_contract = MagicMock()
        mock_contract.constructor.side_effect = Exception("Type mismatch in constructor")
        mock_web3.eth.contract = MagicMock(return_value=mock_contract)
        
        # Act
        result = await prepare_deployment_transaction(
            w3=mock_web3,
            compilation_result=mock_compilation_success,
            deployer_address=valid_deployer_address,
            constructor_params_json='["wrong_type"]',
            gas_limit=3000000
        )
        
        # Assert
        assert result.success == False
        assert "preparar transação" in result.error_message
    
    async def test_error_fetching_nonce(
        self,
        mock_web3,
        mock_compilation_success,
        valid_deployer_address
    ):
        """
        Cenário: Erro ao buscar nonce da rede
        Resultado esperado: success=False, erro ao preparar transação
        """
        from src.besu.services import prepare_deployment_transaction
        
        # Arrange
        mock_web3.to_checksum_address = MagicMock(return_value=valid_deployer_address)
        mock_contract = MagicMock()
        mock_web3.eth.contract = MagicMock(return_value=mock_contract)
        mock_web3.eth.get_transaction_count.side_effect = Exception("Network error")
        
        # Act
        result = await prepare_deployment_transaction(
            w3=mock_web3,
            compilation_result=mock_compilation_success,
            deployer_address=valid_deployer_address,
            constructor_params_json='[]',
            gas_limit=3000000
        )
        
        # Assert
        assert result.success == False
        assert "preparar transação" in result.error_message


@pytest.mark.asyncio
class TestEdgeCases:    
    async def test_transaction_success_without_contract_address(
        self,
        mock_web3,
        valid_signed_transaction,
        mock_tx_hash
    ):
        """
        Cenário: Transação bem-sucedida mas sem contractAddress (não é deploy)
        Resultado esperado: success=True, contract_address=None
        """
        # Arrange
        mock_receipt = MagicMock()
        mock_receipt.status = 1
        mock_receipt.gasUsed = 21000
        # contractAddress não existe (transação normal, não deploy)
        delattr(mock_receipt, 'contractAddress') if hasattr(mock_receipt, 'contractAddress') else None
        
        mock_web3.eth.send_raw_transaction.return_value = mock_tx_hash
        mock_web3.eth.wait_for_transaction_receipt.return_value = mock_receipt
        
        # Act
        result = await broadcast_signed_transaction(mock_web3, valid_signed_transaction)
        
        # Assert
        assert result.success == True
        assert result.contract_address is None
        assert result.gas_used == 21000