import os
import json
from typing import Dict, List, Any, Optional
from web3 import AsyncWeb3
from web3.exceptions import ContractLogicError, TransactionNotFound
from fastapi import UploadFile, HTTPException

from src.besu.schemas import (
    ContractCompilationResponse,
    SignedTransactionResponse
)


async def is_besu_connected(w3: AsyncWeb3):
    return {"status": "ok"} if await w3.is_connected() else {"status": "error"}


async def prepare_deployment_transaction(
    w3: AsyncWeb3,
    compilation_result: ContractCompilationResponse,
    deployer_address: str,
    constructor_params_json: str,
    gas_limit: int
) -> ContractCompilationResponse:
    
    # 1. Validar se a compilação foi bem-sucedida
    if not compilation_result.success:
        return compilation_result
    
    # 2. Parsear constructor_params (vem como JSON string)
    try:
        params = json.loads(constructor_params_json)
        if not isinstance(params, list):
            return ContractCompilationResponse(
                success=False,
                error_message="constructor_params deve ser um array JSON. Ex: [42] ou []"
            )
    except json.JSONDecodeError as e:
        return ContractCompilationResponse(
            success=False,
            error_message=f"Erro ao parsear constructor_params: {str(e)}"
        )
    
    # 3. Validar e converter deployer_address para checksum
    if not deployer_address or not deployer_address.startswith('0x'):
        return ContractCompilationResponse(
            success=False,
            error_message="deployer_address inválido. Deve começar com 0x"
        )
    
    try:
        deployer_address = w3.to_checksum_address(deployer_address)
    except Exception as e:
        return ContractCompilationResponse(
            success=False,
            error_message=f"deployer_address inválido: {str(e)}"
        )
    
    # 4. Criar contrato e encodar construtor com os parâmetros
    try:
        contract = w3.eth.contract(
            abi=compilation_result.abi,
            bytecode=compilation_result.bytecode
        )
        
        if params:
            # Encodar construtor com parâmetros
            data = contract.constructor(*params).data_in_transaction
        else:
            # Sem parâmetros, apenas bytecode
            bytecode = compilation_result.bytecode
            if not bytecode.startswith('0x'):
                bytecode = '0x' + bytecode
            data = bytecode
        
        # 5. Buscar informações da rede para montar a transação
        nonce = await w3.eth.get_transaction_count(deployer_address)
        gas_price = await w3.eth.gas_price
        chain_id = await w3.eth.chain_id
        
        # 6. Montar objeto transaction
        transaction = {
            'from': deployer_address,
            'nonce': nonce,
            'gas': gas_limit,
            'gasPrice': gas_price,
            'data': data,
            'chainId': chain_id,
            'value': 0
        }
        
        # 7. Retornar compilação + transação pronta
        return ContractCompilationResponse(
            success=True,
            abi=compilation_result.abi,
            bytecode=compilation_result.bytecode,
            transaction=transaction,
        )
        
    except Exception as e:
        return ContractCompilationResponse(
            success=False,
            error_message=f"Erro ao preparar transação: {str(e)}"
        )


async def compile_solidity_contract(contract_file: UploadFile) -> ContractCompilationResponse:
    """
    Compila um contrato Solidity usando py-solc-x (compilador Python)
    """
    try:
        from solcx import compile_source, install_solc, set_solc_version
        import re
        
        # Validar extensão do arquivo
        if not contract_file.filename.endswith('.sol'):
            return ContractCompilationResponse(
                success=False,
                error_message="Arquivo deve ter extensão .sol"
            )
        
        # Ler conteúdo do arquivo
        content = await contract_file.read()
        source_code = content.decode('utf-8')
        
        # Detectar versão do Solidity do pragma
        pragma_match = re.search(r'pragma\s+solidity\s+[\^~]?([0-9]+\.[0-9]+\.[0-9]+)', source_code)
        if pragma_match:
            solc_version = pragma_match.group(1)
            
            # LIMITAR VERSÃO MÁXIMA: Solidity 0.8.20+ não é compatível com Besu
            # (usa PUSH0 opcode do Shanghai EVM que Besu não suporta)
            version_parts = list(map(int, solc_version.split('.')))
            if version_parts[0] == 0 and version_parts[1] == 8 and version_parts[2] >= 20:
                solc_version = "0.8.19"  # Downgrade para versão compatível
                print(f"⚠️ Versão {pragma_match.group(1)} não compatível com Besu. Usando 0.8.19")
        else:
            # Tentar detectar apenas major.minor
            pragma_match = re.search(r'pragma\s+solidity\s+[\^~]?([0-9]+\.[0-9]+)', source_code)
            if pragma_match:
                version_parts = pragma_match.group(1)
                # Para versões antigas como ^0.4.8, usar a última versão da série
                if version_parts.startswith('0.4'):
                    solc_version = "0.4.26"  # Última versão 0.4.x
                elif version_parts.startswith('0.5'):
                    solc_version = "0.5.17"  # Última versão 0.5.x
                elif version_parts.startswith('0.6'):
                    solc_version = "0.6.12"  # Última versão 0.6.x
                elif version_parts.startswith('0.7'):
                    solc_version = "0.7.6"   # Última versão 0.7.x
                elif version_parts.startswith('0.8'):
                    solc_version = "0.8.19"  # Versão estável 0.8.x (máximo compatível com Besu)
                else:
                    solc_version = "0.8.19"  # Versão padrão
            else:
                # Versão padrão se não encontrar pragma
                solc_version = "0.8.19"
        
        # Instalar e configurar versão do solc se necessário
        try:
            install_solc(solc_version)
            set_solc_version(solc_version)
        except Exception as version_error:
            # Se falhar, tentar com versão padrão
            try:
                install_solc("0.8.19")
                set_solc_version("0.8.19")
            except Exception as fallback_error:
                return ContractCompilationResponse(
                    success=False,
                    error_message=f"Erro ao instalar compilador Solidity: {str(fallback_error)}"
                )
        
        # Compilar o contrato
        try:
            # Configurar remappings para bibliotecas Solidity (formato correto para py-solc-x)
            import_remappings = [
                '@openzeppelin/contracts=/usr/local/lib/node_modules/@openzeppelin/contracts',
            ]
            
            # Tentar compilar com remappings
            try:
                compiled_sol = compile_source(
                    source_code,
                    import_remappings=import_remappings,
                    allow_paths='/usr/local/lib/node_modules'
                )
            except Exception as e:
                # Se falhar com remappings, tentar sem (para contratos simples)
                compiled_sol = compile_source(source_code)
            
            # Pegar o contrato PRINCIPAL (aquele com maior bytecode)
            # Quando há imports OpenZeppelin, múltiplos contratos são compilados
            # O contrato principal é aquele que tem bytecode deployável (maior tamanho)
            main_contract = None
            max_bytecode_size = 0
            
            for contract_id, contract_interface in compiled_sol.items():
                bytecode_size = len(contract_interface['bin'])
                if bytecode_size > max_bytecode_size:
                    max_bytecode_size = bytecode_size
                    main_contract = (contract_id, contract_interface)
            
            if not main_contract:
                # Fallback: pegar o primeiro contrato
                contract_id, contract_interface = next(iter(compiled_sol.items()))
            else:
                contract_id, contract_interface = main_contract
            
            # Extrair ABI e bytecode
            abi = contract_interface['abi']
            bytecode = contract_interface['bin']
            
            return ContractCompilationResponse(
                success=True,
                abi=abi,
                bytecode=bytecode
            )
            
        except Exception as compile_error:
            error_message = str(compile_error)
            
            # Tratar erros comuns de compilação
            if "DeclarationError" in error_message:
                error_message = f"Erro de declaração no contrato: {error_message}"
            elif "TypeError" in error_message:
                error_message = f"Erro de tipo no contrato: {error_message}"
            elif "SyntaxError" in error_message:
                error_message = f"Erro de sintaxe no contrato: {error_message}"
            
            return ContractCompilationResponse(
                success=False,
                error_message=f"Erro de compilação: {error_message}"
            )
                
    except ImportError:
        return ContractCompilationResponse(
            success=False,
            error_message="Biblioteca py-solc-x não está instalada. Execute: pip install py-solc-x"
        )
    except Exception as e:
        return ContractCompilationResponse(
            success=False,
            error_message=f"Erro interno: {str(e)}"
        )


async def broadcast_signed_transaction(
    w3: AsyncWeb3,
    signed_transaction: str
) -> SignedTransactionResponse:

    try:
        # Verificar conexão
        if not await w3.is_connected():
            return SignedTransactionResponse(
                success=False,
                error_message="Não foi possível conectar ao Besu"
            )
        
        # Validar formato da transação
        if not signed_transaction:
            return SignedTransactionResponse(
                success=False,
                error_message="Transação assinada não fornecida"
            )
        
        # Adicionar '0x' se necessário
        if not signed_transaction.startswith('0x'):
            signed_transaction = '0x' + signed_transaction
        
        # Validar que é um hex válido
        try:
            bytes.fromhex(signed_transaction[2:])
        except ValueError:
            return SignedTransactionResponse(
                success=False,
                error_message="Transação assinada deve estar em formato hexadecimal válido"
            )
        
        # Enviar transação assinada para a rede
        try:
            tx_hash = await w3.eth.send_raw_transaction(signed_transaction)
        except (ValueError, Exception) as e:
            # Erros comuns: nonce incorreto, gas insuficiente, etc.
            error_msg = str(e)
            
            # Tratar erros específicos de gas
            if "gas" in error_msg.lower():
                return SignedTransactionResponse(
                    success=False,
                    error_message=f"Erro de gas: {error_msg}. Verifique o gas_limit."
                )
            elif "nonce" in error_msg.lower():
                return SignedTransactionResponse(
                    success=False,
                    error_message=f"Erro de nonce: {error_msg}. Verifique se o nonce está correto."
                )

            else:
                return SignedTransactionResponse(
                    success=False,
                    error_message=f"Erro ao enviar transação: {error_msg}"
                )
        
        # Aguardar confirmação da transação
        try:
            tx_receipt = await w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        except Exception as e:
            return SignedTransactionResponse(
                success=False,
                transaction_hash=tx_hash.hex(),
                error_message=f"Transação enviada mas ocorreu timeout ao aguardar confirmação: {str(e)}"
            )
        
        # Verificar se a transação foi bem-sucedida
        if tx_receipt.status == 1:
            # Verificar se é um deploy de contrato (tem contractAddress)
            contract_address = tx_receipt.contractAddress if hasattr(tx_receipt, 'contractAddress') else None
            
            return SignedTransactionResponse(
                success=True,
                contract_address=contract_address,
                transaction_hash=tx_hash.hex(),
                gas_used=tx_receipt.gasUsed
            )
        else:
            # Transação revertida
            gas_used = tx_receipt.gasUsed
            
            # Tentar obter informações da transação original
            try:
                tx = await w3.eth.get_transaction(tx_hash)
                gas_limit = tx.gas
                
                # Verificar se ficou sem gas
                if gas_used >= gas_limit * 0.95:
                    error_msg = f"Out of Gas: usou {gas_used}/{gas_limit} gas. Aumente o gas_limit para pelo menos {int(gas_limit * 1.5)}"
                else:
                    error_msg = f"Transação revertida (status=0). Gas usado: {gas_used}/{gas_limit}. Possível erro no construtor do contrato."
            except Exception:
                error_msg = f"Transação revertida (status=0). Gas usado: {gas_used}"
            
            return SignedTransactionResponse(
                success=False,
                error_message=error_msg,
                gas_used=gas_used,
                transaction_hash=tx_hash.hex()
            )
            
    except Exception as e:
        return SignedTransactionResponse(
            success=False,
            error_message=f"Erro interno durante deploy: {str(e)}"
        )


