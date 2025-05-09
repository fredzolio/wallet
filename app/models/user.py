import uuid
from sqlalchemy import Boolean, String
from sqlalchemy.dialects.postgresql import UUID as SQLAlchemyUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base

class User(Base):
    """
    Modelo de usuário para autenticação e identificação.
    """
    
    id: Mapped[uuid.UUID] = mapped_column(SQLAlchemyUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    mfa_secret: Mapped[str | None] = mapped_column(String(32), nullable=True)
    
    # Relacionamentos
    documents = relationship("Document", back_populates="owner", cascade="all, delete-orphan")
    transport_card = relationship("TransportCard", uselist=False, back_populates="owner", cascade="all, delete-orphan")
