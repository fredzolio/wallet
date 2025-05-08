from authlib.integrations.httpx_client import AsyncOAuth2Client
from httpx import AsyncClient
from fastapi import HTTPException, status
import json
from typing import Dict, Any, Optional

from app.core.config import settings

class KeycloakAuth:
    """
    Cliente para integração com Keycloak através do protocolo OAuth2/OIDC.
    Fornece métodos para autenticação, autorização e gerenciamento de usuários.
    """
    
    def __init__(self):
        """Inicializa o cliente Keycloak com as configurações da aplicação."""
        self.server_url = settings.KEYCLOAK_URL
        self.realm = settings.KEYCLOAK_REALM
        self.client_id = settings.KEYCLOAK_CLIENT_ID
        self.client_secret = settings.KEYCLOAK_CLIENT_SECRET
        self.base_url = f"{self.server_url}/realms/{self.realm}"
        self.token_endpoint = f"{self.base_url}/protocol/openid-connect/token"
        self.userinfo_endpoint = f"{self.base_url}/protocol/openid-connect/userinfo"
        self.admin_base = f"{self.server_url}/admin/realms/{self.realm}"
        
    async def get_client_token(self) -> Dict[str, Any]:
        """
        Obtém um token de acesso do Keycloak usando client credentials flow.
        Necessário para acessar endpoints administrativos.
        
        Returns:
            Dict com token de acesso e outras informações
        """
        async with AsyncClient() as client:
            response = await client.post(
                self.token_endpoint,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret
                }
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Falha na autenticação com o Keycloak"
                )
                
            return response.json()
            
    async def authenticate_user(self, username: str, password: str) -> Dict[str, Any]:
        """
        Autentica um usuário no Keycloak usando password grant.
        
        Args:
            username: Nome de usuário (email)
            password: Senha do usuário
            
        Returns:
            Dict com token de acesso e outras informações
        """
        async with AsyncClient() as client:
            response = await client.post(
                self.token_endpoint,
                data={
                    "grant_type": "password",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "username": username,
                    "password": password
                }
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Credenciais inválidas"
                )
                
            return response.json()
            
    async def verify_token(self, token: str) -> Dict[str, Any]:
        """
        Verifica a validade de um token JWT do Keycloak.
        
        Args:
            token: Token JWT a ser verificado
            
        Returns:
            Dict com informações do token decodificado
        """
        async with AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/protocol/openid-connect/token/introspect",
                data={
                    "token": token,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret
                }
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Falha ao verificar token"
                )
                
            token_data = response.json()
            
            if not token_data.get("active", False):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token inválido ou expirado"
                )
                
            return token_data
            
    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """
        Obtém informações do usuário a partir do token de acesso.
        
        Args:
            access_token: Token de acesso JWT
            
        Returns:
            Dict com informações do usuário
        """
        async with AsyncOAuth2Client(token={"access_token": access_token}) as client:
            response = await client.get(self.userinfo_endpoint)
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Falha ao obter informações do usuário"
                )
                
            return response.json()
            
    async def create_user(self, user_data: Dict[str, Any]) -> str:
        """
        Cria um novo usuário no Keycloak.
        
        Args:
            user_data: Dados do usuário a ser criado
            
        Returns:
            ID do usuário criado
        """
        token_data = await self.get_client_token()
        access_token = token_data["access_token"]
        
        user_representation = {
            "enabled": True,
            "username": user_data["email"],
            "email": user_data["email"],
            "firstName": user_data.get("first_name", ""),
            "lastName": user_data.get("last_name", ""),
            "credentials": [
                {
                    "type": "password",
                    "value": user_data["password"],
                    "temporary": False
                }
            ]
        }
        
        async with AsyncClient() as client:
            response = await client.post(
                f"{self.admin_base}/users",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                },
                content=json.dumps(user_representation)
            )
            
            if response.status_code != 201:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Falha ao criar usuário: {response.text}"
                )
                
            # Extrair o ID do usuário da URL de localização
            user_id = response.headers["Location"].split("/")[-1]
            return user_id
            
    async def assign_role(self, user_id: str, role_name: str) -> None:
        """
        Atribui uma role a um usuário.
        
        Args:
            user_id: ID do usuário
            role_name: Nome da role a ser atribuída
        """
        token_data = await self.get_client_token()
        access_token = token_data["access_token"]
        
        # Primeiro, buscar a role pelo nome
        async with AsyncClient() as client:
            response = await client.get(
                f"{self.admin_base}/roles",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Falha ao buscar roles"
                )
                
            roles = response.json()
            role = next((r for r in roles if r["name"] == role_name), None)
            
            if not role:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Role {role_name} não encontrada"
                )
                
            # Atribuir a role ao usuário
            response = await client.post(
                f"{self.admin_base}/users/{user_id}/role-mappings/realm",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                },
                content=json.dumps([role])
            )
            
            if response.status_code != 204:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Falha ao atribuir role ao usuário: {response.text}"
                )
    
    async def get_user_roles(self, user_id: str) -> list:
        """
        Obtém as roles de um usuário.
        
        Args:
            user_id: ID do usuário
            
        Returns:
            Lista de roles do usuário
        """
        token_data = await self.get_client_token()
        access_token = token_data["access_token"]
        
        async with AsyncClient() as client:
            response = await client.get(
                f"{self.admin_base}/users/{user_id}/role-mappings/realm",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Falha ao buscar roles do usuário"
                )
                
            return response.json()

# Instância global para uso em toda a aplicação
keycloak_client = KeycloakAuth() 