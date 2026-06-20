# 🧪 Testes Unitários - Módulo Besu

Este diretório contém testes unitários para as funções do módulo `besu`, focando especialmente no tratamento de erros e exceções.

## 📁 Estrutura

```
test/
├── __init__.py              # Marca o diretório como pacote Python
├── conftest.py              # Fixtures compartilhadas (mocks, dados de teste)
├── test_services.py         # Testes das funções de services.py
└── README.md               # Este arquivo
```

## 🎯 Cobertura de Testes

### `test_services.py`

#### ✅ **TestBroadcastSignedTransaction** (16 testes)

Testa todos os cenários da função `broadcast_signed_transaction`:

**Cenários de Sucesso:**
- ✅ Deploy de contrato bem-sucedido
- ✅ Transação sem prefixo `0x` (auto-correção)
- ✅ Transação sem `contractAddress` (não é deploy)

**Cenários de Erro - Validação:**
- ❌ Besu não conectado
- ❌ Transação vazia
- ❌ Formato hexadecimal inválido

**Cenários de Erro - Gas:**
- ❌ `Intrinsic gas exceeds gas limit` (gas muito baixo)
- ❌ `Out of gas` durante execução
- ❌ Transação revertida por falta de gas (95%+ consumido)

**Cenários de Erro - Nonce:**
- ❌ `Nonce too low` (nonce já usado)
- ❌ `Nonce too high` (gap nas transações)

**Cenários de Erro - Execução:**
- ❌ Timeout ao aguardar confirmação
- ❌ Transação revertida por erro no construtor
- ❌ Transação revertida (sem detalhes disponíveis)
- ❌ Erro genérico ao enviar
- ❌ Exceção inesperada

#### ✅ **TestCompileSolidityContract** (4 testes)

Testa cenários básicos da compilação:

- ✅ Compilação bem-sucedida
- ❌ Extensão de arquivo inválida
- ❌ Erro de sintaxe no Solidity
- ❌ Erro de tipo no Solidity

## 🚀 Como Rodar os Testes

### 1. Instalar Dependências

```bash
# No diretório auth/
pip install pytest pytest-asyncio pytest-mock pytest-cov
```

Ou se estiver usando `uv`:

```bash
uv pip install pytest pytest-asyncio pytest-mock pytest-cov
```

### 2. Rodar Todos os Testes

```bash
# Da raiz do projeto
pytest auth/src/besu/test/

# Ou de dentro do diretório auth/
cd auth
pytest src/besu/test/
```

### 3. Rodar com Verbose (detalhes)

```bash
pytest -v auth/src/besu/test/
```

Saída exemplo:
```
test_services.py::TestBroadcastSignedTransaction::test_success_contract_deployment PASSED
test_services.py::TestBroadcastSignedTransaction::test_besu_not_connected PASSED
test_services.py::TestBroadcastSignedTransaction::test_gas_error_intrinsic_gas_exceeds_limit PASSED
...
```

### 4. Rodar Teste Específico

```bash
# Uma classe inteira
pytest auth/src/besu/test/test_services.py::TestBroadcastSignedTransaction

# Um teste específico
pytest auth/src/besu/test/test_services.py::TestBroadcastSignedTransaction::test_gas_error_intrinsic_gas_exceeds_limit

# Por palavra-chave
pytest -k "gas_error" auth/src/besu/test/
```

### 5. Rodar com Cobertura de Código

```bash
# Gerar relatório de cobertura
pytest --cov=src/besu --cov-report=term --cov-report=html auth/src/besu/test/
```

Saída exemplo:
```
----------- coverage: platform linux, python 3.12.0 -----------
Name                      Stmts   Miss  Cover
---------------------------------------------
src/besu/services.py        145     12    92%
src/besu/schemas.py          25      0   100%
---------------------------------------------
TOTAL                       170     12    93%
```

Depois abra `htmlcov/index.html` no navegador para ver detalhes visuais.

### 6. Rodar em Modo Watch (re-executa ao salvar)

```bash
# Instalar pytest-watch
pip install pytest-watch

# Rodar
ptw auth/src/besu/test/ -- -v
```

## 📊 Interpretando os Resultados

### ✅ Teste Passou

```
test_services.py::TestBroadcastSignedTransaction::test_success_contract_deployment PASSED [1/20]
```

- Função está funcionando como esperado neste cenário

### ❌ Teste Falhou

```
test_services.py::TestBroadcastSignedTransaction::test_gas_error FAILED [2/20]

FAILED test_services.py::TestBroadcastSignedTransaction::test_gas_error
AssertionError: assert False == True
```

- Algo mudou no código e quebrou este cenário
- Verifique o stack trace para entender o problema

### ⚠️ Warnings

```
warnings summary
auth/src/besu/test/test_services.py::TestBroadcastSignedTransaction
  DeprecationWarning: ...
```

- Avisos de código deprecado
- Não causam falha mas devem ser corrigidos

## 🔍 Estrutura de um Teste

```python
async def test_gas_error_intrinsic_gas_exceeds_limit(
    self,
    mock_web3,                      # Fixture: Mock do Web3
    valid_signed_transaction        # Fixture: TX assinada válida
):
    """
    Cenário: Gas limit muito baixo
    Resultado esperado: Erro específico de gas
    """
    # Arrange - Configurar mocks e dados
    mock_web3.eth.send_raw_transaction.side_effect = Exception(
        "Intrinsic gas exceeds gas limit"
    )
    
    # Act - Executar a função sendo testada
    result = await broadcast_signed_transaction(mock_web3, valid_signed_transaction)
    
    # Assert - Verificar o resultado
    assert result.success == False
    assert "gas" in result.error_message.lower()
```

## 🛠️ Adicionar Novos Testes

### 1. Para Erro Novo

```python
async def test_seu_novo_erro(self, mock_web3, valid_signed_transaction):
    """
    Cenário: Descreva o cenário de erro
    Resultado esperado: O que deve acontecer
    """
    # Arrange - Configure o mock para lançar o erro
    mock_web3.eth.send_raw_transaction.side_effect = Exception("Seu erro aqui")
    
    # Act
    result = await broadcast_signed_transaction(mock_web3, valid_signed_transaction)
    
    # Assert - Verifique se o erro foi tratado corretamente
    assert result.success == False
    assert "palavra chave" in result.error_message.lower()
```

### 2. Para Nova Fixture

Adicione em `conftest.py`:

```python
@pytest.fixture
def minha_nova_fixture():
    """Descrição da fixture"""
    return "valor ou mock"
```

## 📈 Boas Práticas

1. **Nome descritivo**: `test_gas_error_intrinsic_gas_exceeds_limit` é melhor que `test_error1`
2. **Docstring**: Explique o cenário e resultado esperado
3. **AAA Pattern**: Arrange, Act, Assert
4. **Um assert principal**: Foque no comportamento principal sendo testado
5. **Isole testes**: Não dependa da ordem de execução
6. **Use fixtures**: Reutilize mocks e dados comuns

## 🐛 Troubleshooting

### Erro: `ModuleNotFoundError: No module named 'src'`

**Solução**: Rode os testes a partir do diretório `auth/`:

```bash
cd auth
pytest src/besu/test/
```

### Erro: `RuntimeError: Event loop is closed`

**Solução**: Instale `pytest-asyncio`:

```bash
pip install pytest-asyncio
```

### Erro: `fixture 'mock_web3' not found`

**Solução**: Certifique-se que `conftest.py` está no mesmo diretório ou pasta pai.

## 📚 Referências

- [pytest Documentation](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [unittest.mock](https://docs.python.org/3/library/unittest.mock.html)
- [Web3.py Testing](https://web3py.readthedocs.io/en/stable/testing.html)

## ✨ Próximos Passos

- [ ] Adicionar testes de integração com Besu real
- [ ] Adicionar testes para `routers.py` (endpoints FastAPI)
- [ ] Configurar CI/CD para rodar testes automaticamente
- [ ] Aumentar cobertura para 95%+
