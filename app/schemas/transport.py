import uuid
from pydantic import BaseModel, Field
from datetime import datetime
from typing import List

class TransportCardBase(BaseModel):
    """Schema base para cartão de transporte."""
    card_number: str = Field(..., description="Número do cartão de transporte")

class TransportCardCreate(TransportCardBase):
    """Schema para criação de cartão de transporte."""
    pass

class TransportCardResponse(TransportCardBase):
    """Schema para resposta com dados do cartão de transporte."""
    id: uuid.UUID
    user_id: uuid.UUID
    balance_centavos: int

    class Config:
        from_attributes = True

class BalanceResponse(BaseModel):
    """Schema para resposta de consulta de saldo."""
    balance_centavos: int
    balance_reais: float
    card_number: str

class RecargaBase(BaseModel):
    """Schema base para recarga."""
    value_centavos: int = Field(..., gt=0, description="Valor da recarga em centavos")

class RecargaCreate(RecargaBase):
    """Schema para criação de recarga."""
    pass

class RecargaResponse(RecargaBase):
    """Schema para resposta com dados da recarga."""
    id: uuid.UUID
    card_id: uuid.UUID
    timestamp: datetime
    value_reais: float

    class Config:
        from_attributes = True

class RecargaList(BaseModel):
    """Schema para listar múltiplas recargas."""
    items: List[RecargaResponse]
    total: int

class ConsumoBase(BaseModel):
    """Schema base para consumo de saldo."""
    value_centavos: int = Field(..., gt=0, description="Valor do consumo em centavos")
    description: str = Field(..., description="Descrição do consumo")

class ConsumoCreate(ConsumoBase):
    """Schema para criação de consumo."""
    pass

class ConsumoResponse(ConsumoBase):
    """Schema para resposta com dados do consumo."""
    id: uuid.UUID
    card_id: uuid.UUID
    timestamp: datetime
    value_reais: float

    class Config:
        from_attributes = True

class ConsumoList(BaseModel):
    """Schema para listar múltiplos consumos."""
    items: List[ConsumoResponse]
    total: int
