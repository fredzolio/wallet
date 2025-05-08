import uuid
from sqlalchemy import String, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as SQLAlchemyUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base

class TransportCard(Base):
    """
    Modelo para o cartão de transporte do usuário.
    Armazena o número do cartão e o saldo atual em centavos.
    """
    
    __tablename__ = "transportcards"
    
    id: Mapped[uuid.UUID] = mapped_column(SQLAlchemyUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(SQLAlchemyUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    card_number: Mapped[str] = mapped_column(String(32), unique=True)  # Número único do cartão
    balance_centavos: Mapped[int] = mapped_column(Integer, default=0)  # Saldo em centavos
    
    # Relacionamentos
    owner = relationship("User", back_populates="transport_card")
    recargas = relationship("Recarga", back_populates="card", cascade="all, delete-orphan")
