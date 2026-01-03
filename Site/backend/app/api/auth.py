"""
Routes d'authentification avec Discord OAuth2.
"""

from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.responses import RedirectResponse
from datetime import timedelta
import logging

from ..core.config import settings
from ..core.security import exchange_discord_code, get_discord_user, create_access_token
from ..core.dependencies import get_current_user
from ..models.user import AuthResponse, UserBase
from ..services.cards_service import card_system

router = APIRouter()
logger = logging.getLogger(__name__)



@router.get("/discord")
async def discord_login():
    """
    Redirige l'utilisateur vers la page d'autorisation Discord.

    Le frontend doit appeler cette route ou construire l'URL directement.
    """
    oauth_url = (
        f"{settings.DISCORD_OAUTH_AUTHORIZE}"
        f"?client_id={settings.DISCORD_CLIENT_ID}"
        f"&redirect_uri={settings.DISCORD_REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=identify"
    )

    return RedirectResponse(url=oauth_url)


@router.get("/login")
async def login():
    """
    Alias pour /discord.
    """
    return await discord_login()



@router.get("/discord/callback")
async def discord_callback(code: str):
    """
    Callback OAuth2 Discord. Échange le code contre un access token.

    Args:
        code: Code d'autorisation reçu de Discord

    Returns:
        AuthResponse avec JWT token et informations utilisateur
    """
    logger.info(f"Début du callback Discord avec code: {code[:10]}...")

    # Échanger le code contre un access token Discord
    token_data = await exchange_discord_code(code)

    if not token_data:
        logger.error("Échec de l'échange du code Discord")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Impossible d'obtenir le token Discord"
        )

    logger.info("✅ Token Discord obtenu avec succès")
    discord_access_token = token_data.get("access_token")

    # Récupérer les informations de l'utilisateur
    discord_user = await get_discord_user(discord_access_token)

    if not discord_user:
        logger.error("Échec de la récupération des données utilisateur Discord")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Impossible de récupérer les informations utilisateur"
        )

    logger.info(f"✅ Données Discord reçues: {discord_user}")

    # Extraire les données Discord
    # IMPORTANT: user_id doit rester une string pour eviter la perte de precision en JavaScript
    # (les IDs Discord depassent 2^53, limite des nombres JS)
    user_data = {
        "user_id": discord_user["id"],  # Garder comme string!
        "username": discord_user["username"],
        "discriminator": discord_user.get("discriminator", "0"),
        "global_name": discord_user.get("global_name"),
        "avatar": discord_user.get("avatar"),
    }

    logger.info(f"Utilisateur connecte: {user_data['username']} (ID: {user_data['user_id']}) - Avatar: {user_data['avatar']}")

    # Mettre a jour le cache des utilisateurs pour afficher les pseudos dans les echanges
    try:
        card_system.update_user_cache(
            int(user_data['user_id']),  # Convertir en int pour le cache
            user_data['username'],
            user_data.get('global_name')
        )
    except Exception as e:
        logger.warning(f"Impossible de mettre a jour le cache utilisateur: {e}")

    # Créer un JWT token pour notre API
    access_token_expires = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data=user_data,
        expires_delta=access_token_expires
    )

    # Retourner le token et les infos utilisateur
    return AuthResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserBase(**user_data),
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    """
    Récupère les informations de l'utilisateur actuellement connecté.

    Requires: Bearer token dans le header Authorization

    Returns:
        Informations de l'utilisateur (depuis le JWT token)
    """
    return UserBase(**current_user)


@router.post("/logout")
async def logout(current_user: dict = Depends(get_current_user)):
    """
    Déconnecte l'utilisateur.

    Note: Comme nous utilisons des JWT stateless, la "déconnexion" se fait
    côté client en supprimant le token. Cette route sert principalement
    à valider le token avant la déconnexion.
    """
    logger.info(f"Utilisateur déconnecté: {current_user['username']} (ID: {current_user['user_id']})")
    return {"message": "Déconnexion réussie"}


@router.get("/status")
async def auth_status(current_user: dict = Depends(get_current_user)):
    """
    Vérifie si l'utilisateur est authentifié et si son token est valide.
    """
    return {
        "authenticated": True,
        "user_id": current_user["user_id"],
        "username": current_user["username"]
    }
