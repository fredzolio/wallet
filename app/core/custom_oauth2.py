from fastapi.security import OAuth2PasswordBearer
from fastapi.security.utils import get_authorization_scheme_param
from fastapi import Request, HTTPException, status
from typing import Optional, Dict, Any

class OAuth2MfaBearer(OAuth2PasswordBearer):
    """
    OAuth2 esquema personalizado que suporta autenticação MFA no Swagger.
    """
    def __init__(
        self,
        tokenUrl: str,
        scheme_name: Optional[str] = None,
        description: Optional[str] = None,
        auto_error: bool = True,
    ):
        super().__init__(tokenUrl=tokenUrl, scheme_name=scheme_name, description=description, auto_error=auto_error)
        self._token_url = tokenUrl

    async def __call__(self, request: Request) -> Optional[str]:
        """
        Obtém o token de autorização da requisição.
        """
        authorization = request.headers.get("Authorization")
        scheme, param = get_authorization_scheme_param(authorization)
        
        if not authorization or scheme.lower() != "bearer":
            if self.auto_error:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Não autenticado",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            else:
                return None
        
        return param
    
    @property
    def openapi_flow_scopes(self) -> Dict[str, Any]:
        """
        Define o fluxo OAuth2 personalizado para o Swagger.
        """
        return {
            "type": "oauth2",
            "flows": {
                "password": {
                    "tokenUrl": self._token_url,
                    "scopes": {}
                }
            }
        } 