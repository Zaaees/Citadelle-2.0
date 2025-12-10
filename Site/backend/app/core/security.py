"""
Fonctions de sécurité pour JWT, hashing, et authentification.
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from passlib.context import CryptContext
import httpx

from .config import settings

# Context pour le hashing de mots de passe (si nécessaire plus tard)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Crée un JWT access token.

    Args:
        data: Données à encoder dans le token (user_id, username, etc.)
        expires_delta: Durée de validité du token

    Returns:
        str: JWT token encodé
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire, "iat": datetime.utcnow()})

    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )

    return encoded_jwt


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Décode et valide un JWT token.

    Args:
        token: JWT token à décoder

    Returns:
        Dict contenant les données du token ou None si invalide
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except JWTError:
        return None


async def exchange_discord_code(code: str) -> Optional[Dict[str, Any]]:
    """
    Échange le code OAuth2 Discord contre un access token.

    Args:
        code: Code d'autorisation reçu de Discord

    Returns:
        Dict contenant access_token, token_type, etc. ou None si échec
    """
    data = {
        "client_id": settings.DISCORD_CLIENT_ID,
        "client_secret": settings.DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.DISCORD_REDIRECT_URI,
    }

    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                settings.DISCORD_OAUTH_TOKEN,
                data=data,
                headers=headers
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError:
            return None


async def get_discord_user(access_token: str) -> Optional[Dict[str, Any]]:
    """
    Récupère les informations de l'utilisateur Discord avec son access token.

    Args:
        access_token: Access token Discord OAuth2

    Returns:
        Dict contenant id, username, avatar, etc. ou None si échec
    """
    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{settings.DISCORD_API_ENDPOINT}/users/@me",
                headers=headers
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError:
            return None


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Vérifie un mot de passe hashé (pour usage futur si nécessaire)."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash un mot de passe (pour usage futur si nécessaire)."""
    return pwd_context.hash(password)
