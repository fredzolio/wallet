import uuid
from sqlalchemy import Integer, ForeignKey, DateTime, func, String
from sqlalchemy.dialects.postgresql import UUID as SQLAlchemyUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from sqlalchemy.ext.declarative import declared_attr

from app.db.base_class import Base

class Consumo(Base):
    """
    Modelo para registrar os consumos do cartão de transporte.
    Armazena o valor do consumo, a descrição e o momento em que foi realizado.
    """
    
    # Sobrescrever corretamente o método __tablename__
    @declared_attr.directive
    def __tablename__(cls) -> str:
        return "consumos"
    
    id: Mapped[uuid.UUID] = mapped_column(SQLAlchemyUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    card_id: Mapped[uuid.UUID] = mapped_column(SQLAlchemyUUID(as_uuid=True), ForeignKey("transportcards.id", ondelete="CASCADE"))
    value_centavos: Mapped[int] = mapped_column(Integer)  # Valor do consumo em centavos
    description: Mapped[str] = mapped_column(String(255))  # Descrição do consumo
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    # Relacionamento
    card = relationship("TransportCard", back_populates="consumos") 