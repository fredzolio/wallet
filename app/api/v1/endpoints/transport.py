from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.session import get_db
from app.api.v1.deps import limiter, redis
from app.models.transport import TransportCard
from app.models.recarga import Recarga
from app.models.consumo import Consumo
from app.models.user import User
from app.schemas.transport import (
    TransportCardCreate, 
    TransportCardResponse,
    BalanceResponse,
    RecargaCreate,
    RecargaResponse,
    RecargaList,
    ConsumoCreate,
    ConsumoResponse,
    ConsumoList
)

router = APIRouter(prefix="/transport")

def centavos_para_reais(centavos: int) -> float:
    """Converte valor em centavos para reais (formato float)."""
    return centavos / 100.0

@router.post("/card", response_model=TransportCardResponse, status_code=status.HTTP_201_CREATED)
async def create_card(
    card_in: TransportCardCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Cria um novo cartão de transporte para o usuário atual.
    """
    # Verificar se o usuário já tem cartão
    if current_user.transport_card:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuário já possui um cartão de transporte"
        )
    
    # Verificar se o número do cartão já existe
    result = await db.execute(select(TransportCard).where(TransportCard.card_number == card_in.card_number))
    existing_card = result.scalar_one_or_none()
    
    if existing_card:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Número de cartão já registrado"
        )
    
    # Criar o cartão
    card = TransportCard(
        user_id=current_user.id,
        card_number=card_in.card_number,
        balance_centavos=0
    )
    
    db.add(card)
    await db.commit()
    await db.refresh(card)
    
    return card

@router.get("/card", response_model=TransportCardResponse)
async def get_card(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Obtém os dados do cartão de transporte do usuário atual.
    """
    # Verificar se o usuário tem cartão
    if not current_user.transport_card:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não possui cartão de transporte"
        )
    
    return current_user.transport_card

@router.get("/balance", response_model=BalanceResponse)
async def get_balance(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Consulta o saldo do cartão de transporte do usuário atual.
    """
    # Verificar se o usuário tem cartão
    if not current_user.transport_card:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não possui cartão de transporte"
        )
    
    card = current_user.transport_card
    
    return BalanceResponse(
        balance_centavos=card.balance_centavos,
        balance_reais=centavos_para_reais(card.balance_centavos),
        card_number=card.card_number
    )

@router.post("/recharge", response_model=RecargaResponse)
@limiter.limit("5/minute")
async def recharge(
    request: Request,
    recarga_in: RecargaCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Realiza uma recarga no cartão de transporte do usuário atual.
    
    Exemplo:
    ```json
    {
        "value_centavos": 1000  // R$ 10,00
    }
    ```
    """
    # Verificar se o usuário tem cartão
    if not current_user.transport_card:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não possui cartão de transporte"
        )
    
    card = current_user.transport_card
    
    # Adquirir lock distribuído para evitar condições de corrida
    async with redis.lock(f"card_recharge:{card.id}", timeout=10):
        # Registrar a recarga
        recarga = Recarga(
            card_id=card.id,
            value_centavos=recarga_in.value_centavos
        )
        
        # Atualizar o saldo do cartão
        card.balance_centavos += recarga_in.value_centavos
        
        db.add(recarga)
        await db.commit()
        await db.refresh(recarga)
    
    # Adicionar valor em reais para a resposta
    setattr(recarga, "value_reais", centavos_para_reais(recarga.value_centavos))
    
    return recarga

@router.post("/consume", response_model=ConsumoResponse)
@limiter.limit("10/minute")
async def consume(
    request: Request,
    consumo_in: ConsumoCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Registra um consumo no cartão de transporte do usuário atual.
    
    Exemplo:
    ```json
    {
        "value_centavos": 450,  // R$ 4,50
        "description": "Passagem de ônibus"
    }
    ```
    """
    # Verificar se o usuário tem cartão
    if not current_user.transport_card:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não possui cartão de transporte"
        )
    
    card = current_user.transport_card
    
    # Adquirir lock distribuído para evitar condições de corrida
    async with redis.lock(f"card_consume:{card.id}", timeout=10):
        # Verificar se há saldo suficiente
        if card.balance_centavos < consumo_in.value_centavos:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Saldo insuficiente"
            )
        
        # Registrar o consumo
        consumo = Consumo(
            card_id=card.id,
            value_centavos=consumo_in.value_centavos,
            description=consumo_in.description
        )
        
        # Atualizar o saldo do cartão
        card.balance_centavos -= consumo_in.value_centavos
        
        db.add(consumo)
        await db.commit()
        await db.refresh(consumo)
    
    # Adicionar valor em reais para a resposta
    setattr(consumo, "value_reais", centavos_para_reais(consumo.value_centavos))
    
    return consumo

@router.get("/recharges", response_model=RecargaList)
async def list_recharges(
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Lista o histórico de recargas do cartão de transporte do usuário atual.
    """
    # Verificar se o usuário tem cartão
    if not current_user.transport_card:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não possui cartão de transporte"
        )
    
    card = current_user.transport_card
    
    # Buscar recargas
    query = select(Recarga).where(Recarga.card_id == card.id)
    query = query.order_by(Recarga.timestamp.desc()).offset(skip).limit(limit)
    
    result = await db.execute(query)
    recargas = result.scalars().all()
    
    # Adicionar value_reais para cada recarga
    for recarga in recargas:
        setattr(recarga, "value_reais", centavos_para_reais(recarga.value_centavos))
    
    # Contar total
    count_query = select(func.count(Recarga.id)).where(Recarga.card_id == card.id)
    count_result = await db.execute(count_query)
    total = count_result.scalar()
    
    # Converter para lista de RecargaResponse para atender à tipagem esperada
    recarga_responses = [RecargaResponse.model_validate(recarga) for recarga in recargas]
    
    return RecargaList(
        items=recarga_responses,
        total=total or 0  # Garantir que total é sempre int, não int | None
    )

@router.get("/consumos", response_model=ConsumoList)
async def list_consumos(
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Lista o histórico de consumos do cartão de transporte do usuário atual.
    """
    # Verificar se o usuário tem cartão
    if not current_user.transport_card:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não possui cartão de transporte"
        )
    
    card = current_user.transport_card
    
    # Buscar consumos
    query = select(Consumo).where(Consumo.card_id == card.id)
    query = query.order_by(Consumo.timestamp.desc()).offset(skip).limit(limit)
    
    result = await db.execute(query)
    consumos = result.scalars().all()
    
    # Adicionar value_reais para cada consumo
    for consumo in consumos:
        setattr(consumo, "value_reais", centavos_para_reais(consumo.value_centavos))
    
    # Contar total
    count_query = select(func.count(Consumo.id)).where(Consumo.card_id == card.id)
    count_result = await db.execute(count_query)
    total = count_result.scalar()
    
    # Converter para lista de ConsumoResponse para atender à tipagem esperada
    consumo_responses = [ConsumoResponse.model_validate(consumo) for consumo in consumos]
    
    return ConsumoList(
        items=consumo_responses,
        total=total or 0  # Garantir que total é sempre int, não int | None
    )
