from pydantic import BaseModel
from typing import List, Optional, Any, Dict

class BesuStatus(BaseModel):
    status: str

class ContractCompilationResponse(BaseModel):
    success: bool
    abi: Optional[List[Dict]] = None
    bytecode: Optional[str] = None
    transaction: Optional[Dict[str, Any]] = None  # Objeto transaction para assinar
    error_message: Optional[str] = None

class SignedTransactionRequest(BaseModel):

    signed_transaction: str  # Raw transaction em hexadecimal (com ou sem 0x)

class SignedTransactionResponse(BaseModel):
    """
    Resposta do broadcast de uma transação assinada
    """
    success: bool
    contract_address: Optional[str] = None
    transaction_hash: Optional[str] = None
    gas_used: Optional[int] = None
    error_message: Optional[str] = None