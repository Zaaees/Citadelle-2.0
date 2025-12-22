"""
Routes pour les informations et statistiques utilisateur.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Dict, Any
import logging
import asyncio

from ..core.dependencies import get_current_user
from ..models.card import UserCollection, CardDiscovery
from ..services.cards_service import card_system

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/collection", response_model=UserCollection)
async def get_user_collection(current_user: dict = Depends(get_current_user)):
    """
    Recupere la collection complete de l'utilisateur.

    Returns:
        Collection de cartes avec nombre d'exemplaires et statistiques
    """
    user_id = current_user["user_id"]  # int pour les services
    user_id_str = current_user["user_id_str"]  # string pour la réponse API

    logger.info(f"Recuperation de la collection pour l'utilisateur {user_id}")

    try:
        collection_data = await card_system.get_user_collection(user_id)

        return UserCollection(
            user_id=user_id_str,
            cards=collection_data["cards"],
            total_cards=collection_data["total_cards"],
            unique_cards=collection_data["unique_cards"],
            completion_percentage=collection_data["completion_percentage"]
        )

    except Exception as e:
        logger.error(f"Erreur lors de la recuperation de la collection: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la recuperation de la collection"
        )


@router.get("/stats")
async def get_user_stats(current_user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """
    Recupere les statistiques completes de l'utilisateur.

    Returns:
        Statistiques detaillees (collection, tirages, echanges, etc.)
    """
    user_id = current_user["user_id"]  # int pour les services
    user_id_str = current_user["user_id_str"]  # string pour la réponse API

    logger.info(f"Recuperation des stats pour l'utilisateur {user_id}")

    try:
        stats = await card_system.get_user_stats(user_id)

        # Ajouter les infos utilisateur (user_id_str pour éviter perte de précision JS)
        stats["user"] = {
            "user_id": user_id_str,
            "username": current_user.get("username", ""),
            "avatar": current_user.get("avatar"),
            "global_name": current_user.get("global_name")
        }

        return stats

    except Exception as e:
        logger.error(f"Erreur lors de la recuperation des stats: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la recuperation des statistiques"
        )


@router.get("/discoveries", response_model=List[CardDiscovery])
async def get_user_discoveries(current_user: dict = Depends(get_current_user)):
    """
    Recupere les cartes decouvertes en premier par l'utilisateur.

    Returns:
        Liste des decouvertes de l'utilisateur
    """
    user_id = current_user["user_id"]  # int
    user_id_str = current_user["user_id_str"]  # string pour comparaison avec sheet

    logger.info(f"Recuperation des decouvertes pour l'utilisateur {user_id}")

    try:
        discoveries_data = card_system.storage.sheet_discoveries.get_all_values()[1:]

        discoveries = []
        for row in discoveries_data:
            # Format: category, name, discoverer_id, discoverer_name, timestamp, discovery_index
            if len(row) >= 6 and row[2] == user_id_str:
                discoveries.append(CardDiscovery(
                    category=row[0],
                    name=row[1],
                    discoverer_id=int(row[2]),
                    discoverer_name=row[3],
                    timestamp=row[4],
                    discovery_index=int(row[5]) if row[5] else 0
                ))

        return discoveries

    except Exception as e:
        logger.error(f"Erreur lors de la recuperation des decouvertes: {e}")
        return []


@router.get("/vault")
async def get_user_vault(current_user: dict = Depends(get_current_user)):
    """
    Recupere le contenu du vault de l'utilisateur.

    Returns:
        Liste des cartes dans le vault
    """
    user_id = current_user["user_id"]  # int pour les services

    logger.info(f"Recuperation du vault pour l'utilisateur {user_id}")

    try:
        vault_cards = await asyncio.to_thread(
            card_system.vault_manager.get_user_vault_cards,
            user_id
        )

        # Convertir en format dict pour la reponse
        vault_data = [
            {"category": cat, "name": name}
            for cat, name in vault_cards
        ]

        return vault_data

    except Exception as e:
        logger.error(f"Erreur lors de la recuperation du vault: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la recuperation du vault"
        )
