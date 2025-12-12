"""
Routes pour la gestion du vault (coffre) des utilisateurs.
"""

from fastapi import APIRouter, Depends, HTTPException, status
import logging
import asyncio

from ..core.dependencies import get_current_user
from ..services.cards_service import card_system

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/deposit")
async def deposit_to_vault(
    category: str,
    name: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Depose une carte dans le vault de l'utilisateur.

    Args:
        category: Categorie de la carte
        name: Nom de la carte

    Returns:
        Message de confirmation
    """
    user_id = current_user["user_id"]

    logger.info(f"Depot dans le vault par {user_id}: {category}/{name}")

    try:
        # Verifier que l'utilisateur possede la carte
        has_card = card_system._user_has_card(user_id, category, name)
        if not has_card:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Vous ne possedez pas cette carte"
            )

        # Verifier que ce n'est pas une carte Full
        if "(Full)" in name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Les cartes Full ne peuvent pas etre deposees dans le vault"
            )

        # Retirer la carte de la collection
        removed = card_system._remove_card_from_user(user_id, category, name)
        if not removed:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erreur lors du retrait de la carte de votre collection"
            )

        # Ajouter au vault
        success = await asyncio.to_thread(
            card_system.vault_manager.add_card_to_vault,
            user_id,
            category,
            name,
            True  # skip_possession_check car on vient de verifier
        )

        if not success:
            # Remettre la carte si echec
            card_system._add_card_to_user(user_id, category, name)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erreur lors du depot dans le vault"
            )

        return {
            "message": f"Carte {name} deposee dans le vault",
            "success": True
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors du depot: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors du depot dans le vault"
        )


@router.post("/withdraw")
async def withdraw_from_vault(
    category: str,
    name: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Retire une carte du vault de l'utilisateur.

    Args:
        category: Categorie de la carte
        name: Nom de la carte

    Returns:
        Message de confirmation
    """
    user_id = current_user["user_id"]

    logger.info(f"Retrait du vault par {user_id}: {category}/{name}")

    try:
        # Retirer du vault
        success = await asyncio.to_thread(
            card_system.vault_manager.remove_card_from_vault,
            user_id,
            category,
            name
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cette carte n'est pas dans votre vault"
            )

        # Ajouter a la collection
        added = card_system._add_card_to_user(user_id, category, name)
        if not added:
            # Remettre dans le vault si echec
            card_system.vault_manager.add_card_to_vault(user_id, category, name, True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erreur lors de l'ajout a votre collection"
            )

        return {
            "message": f"Carte {name} retiree du vault",
            "success": True
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors du retrait: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors du retrait du vault"
        )


@router.get("/cards")
async def get_vault_cards(current_user: dict = Depends(get_current_user)):
    """
    Recupere les cartes dans le vault de l'utilisateur.

    Returns:
        Liste des cartes dans le vault avec leur quantite
    """
    user_id = current_user["user_id"]

    logger.info(f"Recuperation du vault pour {user_id}")

    try:
        vault_cards = await asyncio.to_thread(
            card_system.vault_manager.get_user_vault_cards,
            user_id
        )

        # Compter les cartes
        from collections import Counter
        card_counts = Counter(vault_cards)

        cards = [
            {
                "category": cat,
                "name": name,
                "count": count
            }
            for (cat, name), count in card_counts.items()
        ]

        return {
            "user_id": str(user_id),
            "cards": cards,
            "total_cards": len(vault_cards)
        }

    except Exception as e:
        logger.error(f"Erreur lors de la recuperation du vault: {e}")
        return {
            "user_id": str(user_id),
            "cards": [],
            "total_cards": 0
        }
