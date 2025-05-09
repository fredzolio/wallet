import uuid
from sqlalchemy import Integer, ForeignKey, DateTime, func
from sqlalchemy.dialects.postgresql import UUID as SQLAlchemyUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from sqlalchemy.ext.declarative import declared_attr

from app.db.base_class import Base

class Recarga(Base):
    """
    Modelo para registrar as recargas do cartão de transporte.
    Armazena o valor da recarga e o momento em que foi realizada.
    """
    
    # Sobrescrever corretamente o método __tablename__
    @declared_attr.directive
    def __tablename__(cls) -> str:
        return "recargas"
    
    id: Mapped[uuid.UUID] = mapped_column(SQLAlchemyUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    card_id: Mapped[uuid.UUID] = mapped_column(SQLAlchemyUUID(as_uuid=True), ForeignKey("transportcards.id", ondelete="CASCADE"))
    value_centavos: Mapped[int] = mapped_column(Integer)  # Valor da recarga em centavos
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    # Relacionamento
    card = relationship("TransportCard", back_populates="recargas")
