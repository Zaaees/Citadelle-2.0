"""
Dépendances FastAPI réutilisables pour l'authentification et la validation.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Dict, Any

from .security import decode_access_token

# Bearer token security scheme
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict[str, Any]:
    """
    Dépendance FastAPI pour récupérer l'utilisateur actuel depuis le JWT token.

    Args:
        credentials: Credentials HTTP Bearer extraites automatiquement du header

    Returns:
        Dict contenant les informations de l'utilisateur (user_id, username, etc.)

    Raises:
        HTTPException 401: Si le token est invalide ou expiré
    """
    token = credentials.credentials

    payload = decode_access_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou expiré",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Vérifier que le payload contient les champs requis
    user_id = payload.get("user_id")
    username = payload.get("username")

    if not user_id or not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide: données utilisateur manquantes",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # user_id est stocké comme string dans le JWT pour éviter la perte de précision
    # mais les services internes attendent un int - on fournit les deux
    return {
        "user_id": int(user_id),  # int pour les services internes
        "user_id_str": str(user_id),  # string pour les réponses API (évite perte de précision JS)
        "username": username,
        "discriminator": payload.get("discriminator", "0"),
        "avatar": payload.get("avatar"),
        "global_name": payload.get("global_name"),
    }


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        HTTPBearer(auto_error=False)
    )
) -> Optional[Dict[str, Any]]:
    """
    Dépendance FastAPI optionnelle pour récupérer l'utilisateur actuel.
    Contrairement à get_current_user, ne lève pas d'exception si pas de token.

    Args:
        credentials: Credentials HTTP Bearer (optionnelles)

    Returns:
        Dict contenant les informations de l'utilisateur ou None si pas authentifié
    """
    if credentials is None:
        return None

    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None
