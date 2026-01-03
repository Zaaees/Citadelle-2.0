"""
Authentification Discord OAuth2
Permet aux utilisateurs de se connecter avec leur compte Discord
"""

import httpx
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from config import get_settings
from models import DiscordUser, Token, TokenData

settings = get_settings()
security = HTTPBearer(auto_error=False)

# URLs Discord OAuth2
DISCORD_API_URL = "https://discord.com/api/v10"
DISCORD_OAUTH_URL = "https://discord.com/api/oauth2"


def get_oauth_url(state: str = "") -> str:
    """Génère l'URL d'autorisation Discord"""
    import urllib.parse
    params = {
        "client_id": settings.discord_client_id,
        "redirect_uri": settings.discord_redirect_uri,
        "response_type": "code",
        "scope": "identify",
    }
    if state:
        params["state"] = state
    query = urllib.parse.urlencode(params)
    return f"{DISCORD_OAUTH_URL}/authorize?{query}"


async def exchange_code(code: str) -> Optional[dict]:
    """Échange le code d'autorisation contre un token d'accès Discord"""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{DISCORD_OAUTH_URL}/token",
                data={
                    "client_id": settings.discord_client_id,
                    "client_secret": settings.discord_client_secret,
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": settings.discord_redirect_uri,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if response.status_code == 200:
                return response.json()
            else:
                print(f"Discord OAuth error: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            print(f"Error exchanging code: {e}")
            return None


async def get_discord_user(access_token: str) -> Optional[DiscordUser]:
    """Récupère les informations de l'utilisateur Discord"""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{DISCORD_API_URL}/users/@me",
                headers={"Authorization": f"Bearer {access_token}"},
            )

            if response.status_code == 200:
                data = response.json()
                return DiscordUser(
                    id=data["id"],
                    username=data["username"],
                    discriminator=data.get("discriminator", "0"),
                    avatar=data.get("avatar"),
                    global_name=data.get("global_name"),
                )
            else:
                print(f"Discord API error: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            print(f"Error getting Discord user: {e}")
            return None


def create_access_token(user: DiscordUser) -> str:
    """Crée un token JWT pour l'utilisateur"""
    expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode = {
        "sub": user.id,
        "username": user.username,
        "avatar": user.avatar,
        "exp": expire,
    }
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> Optional[TokenData]:
    """Décode et valide un token JWT"""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        user_id = payload.get("sub")
        username = payload.get("username")
        avatar = payload.get("avatar")

        if user_id is None:
            return None

        return TokenData(user_id=user_id, username=username, avatar=avatar)
    except JWTError:
        return None


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[TokenData]:
    """
    Récupère l'utilisateur courant depuis le token JWT
    Vérifie d'abord le header Authorization, puis le cookie
    """
    token = None

    # Vérifier le header Authorization
    if credentials:
        token = credentials.credentials

    # Sinon, vérifier le cookie
    if not token:
        token = request.cookies.get("access_token")

    if not token:
        return None

    return decode_token(token)


async def require_auth(
    current_user: Optional[TokenData] = Depends(get_current_user)
) -> TokenData:
    """Dépendance qui requiert une authentification"""
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Non authentifié",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return current_user
