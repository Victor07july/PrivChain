from web3 import Web3
from eth_account import Account
import json

# ===========================
# CONFIGURAÇÃO
# ===========================

# Cole aqui o objeto 'transaction' retornado pela API
TRANSACTION = {
        "from": "0xFE3B557E8Fb62b89F4916B721be55cEb828dBd73",
        "nonce": 0,
        "gas": 3000000,
        "gasPrice": 0,
        "data": "0x608060405234801561001057600080fd5b506040516102fb3803806102fb833981810160405281019061003291906100c8565b806000819055503373ffffffffffffffffffffffffffffffffffffffff167fe42ab83e51dcfb436887e998d12b1585d6eea49b2900b0b3bcd0591dec7c3d198260405161007f9190610104565b60405180910390a25061011f565b600080fd5b6000819050919050565b6100a581610092565b81146100b057600080fd5b50565b6000815190506100c28161009c565b92915050565b6000602082840312156100de576100dd61008d565b5b60006100ec848285016100b3565b91505092915050565b6100fe81610092565b82525050565b600060208201905061011960008301846100f5565b92915050565b6101cd8061012e6000396000f3fe608060405234801561001057600080fd5b50600436106100415760003560e01c80632a1afcd91461004657806360fe47b1146100645780636d4ce63c14610080575b600080fd5b61004e61009e565b60405161005b919061011e565b60405180910390f35b61007e6004803603810190610079919061016a565b6100a4565b005b6100886100fc565b604051610095919061011e565b60405180910390f35b60005481565b806000819055503373ffffffffffffffffffffffffffffffffffffffff167fe42ab83e51dcfb436887e998d12b1585d6eea49b2900b0b3bcd0591dec7c3d19826040516100f1919061011e565b60405180910390a250565b60008054905090565b6000819050919050565b61011881610105565b82525050565b6000602082019050610133600083018461010f565b92915050565b600080fd5b61014781610105565b811461015257600080fd5b50565b6000813590506101648161013e565b92915050565b6000602082840312156101805761017f610139565b5b600061018e84828501610155565b9150509291505056fea264697066735822122043071242007a81bc30e6ff73e1130c05b04bf48b08c4b2767bd490a8e0e601e964736f6c634300080a0033000000000000000000000000000000000000000000000000000000000000002a",
        "chainId": 1337,
        "value": 0
}

# Sua chave privada
PRIVATE_KEY = "0xfe3b557e8fb62b89f4916b721be55ceb828dbd73"

# ===========================
# SCRIPT
# ===========================

def main():
    
    # Adicionar 0x se necessário
    if not PRIVATE_KEY.startswith('0x'):
        private_key = '0x' + PRIVATE_KEY
    else:
        private_key = PRIVATE_KEY
    
    # Gerar conta a partir da chave privada
    try:
        account = Account.from_key(private_key)
    except Exception as e:
        print(f" Erro ao criar conta: {e}")
        print("   Verifique se a chave privada está correta")
        return
    
    print(f"Conta: {account.address}")
    
    # Verificar se o endereço 'from' na transação corresponde à conta
    if TRANSACTION['from'].lower() != account.address.lower():
        print(f"\n  ATENÇÃO: Endereço 'from' na transação ({TRANSACTION['from']}) ")
        print(f"    não corresponde à sua conta ({account.address})")
        print("    A transação pode falhar!")
        response = input("\nContinuar mesmo assim? (s/n): ")
        if response.lower() != 's':
            print("Operação cancelada.")
            return
    
    # Assinar transação
    print(f"\n Assinando transação...")
    try:
        signed = account.sign_transaction(TRANSACTION)
        signed_tx_hex = signed.raw_transaction.hex()
        tx_hash = signed.hash.hex()
    except Exception as e:
        print(f" Erro ao assinar transação: {e}")
        return
    
    print(f" Transação assinada com sucesso!")
    print(f"   Hash previsto: {tx_hash}")
    
    # ===========================
    # RESULTADO PARA COPIAR E COLAR NO POSTMAN
    # ===========================

    
    print("\n Body (raw JSON):")
    body = {
        "signed_transaction": signed_tx_hex
    }
    print(json.dumps(body, indent=2))
    
    print("\n" + "=" * 70)
    print("📝 APENAS A TRANSAÇÃO ASSINADA (copie facilmente):")
    print("=" * 70)
    print(signed_tx_hex)
    
    # Salvar em arquivo
    output_data = {
        "signed_transaction": signed_tx_hex,
        "transaction_hash_preview": tx_hash,
        "deployer_address": account.address,
        "nonce": TRANSACTION['nonce'],
        "gas_limit": TRANSACTION['gas'],
        "gas_price": TRANSACTION['gasPrice'],
        "chain_id": TRANSACTION['chainId']
    }
    
    output_file = "signed_transaction_api.json"
    with open(output_file, 'w') as f:
        json.dump(output_data, f, indent=2)
    
    print(f"\n💾 Dados salvos em: {output_file}")
    
 

if __name__ == "__main__":
    main()