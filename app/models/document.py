import uuid
from datetime import datetime
from sqlalchemy import String, ForeignKey, DateTime, JSON, func
from sqlalchemy.dialects.postgresql import UUID as SQLAlchemyUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base

class Document(Base):
    """
    Modelo para armazenar documentos digitais dos usuários.
    O conteúdo é armazenado como JSON para flexibilidade.
    """
    
    id: Mapped[uuid.UUID] = mapped_column(SQLAlchemyUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(SQLAlchemyUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(50))  # Tipo do documento (CPF, RG, etc.)
    content_json: Mapped[dict] = mapped_column(JSON)  # Conteúdo do documento em formato JSON
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    # Relacionamento
    owner = relationship("User", back_populates="documents")
