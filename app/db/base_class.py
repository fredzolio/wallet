from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    """
    Classe base para todos os modelos SQLAlchemy.
    
    Fornece uma implementação padrão para o nome da tabela 
    (automático a partir do nome da classe).
    """
    
    # Gera automaticamente o nome da tabela a partir do nome da classe
    @declared_attr.directive
    def __tablename__(cls) -> str:
        return cls.__name__.lower() + "s" 