"""
Routes pour les echanges de cartes.
Implemente le Tableau d'Echanges et les echanges hebdomadaires.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
import logging
import asyncio
from datetime import datetime

from ..core.dependencies import get_current_user
from ..models.trade import (
    TradeOffer, TradeOfferCreate, TradeProposal,
    DirectTradeRequest, TradeHistory, VaultTradeRequest
)
from ..services.cards_service import card_system

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/board", response_model=List[TradeOffer])
async def get_trade_board():
    """
    Recupere toutes les offres actuellement sur le tableau d'echanges.

    Returns:
        Liste des offres disponibles
    """
    logger.info("Recuperation du tableau d'echanges")

    try:
        # Utiliser le TradingManager du bot
        entries = await asyncio.to_thread(
            card_system.trading_manager.list_board_offers
        )

        offers = []
        for entry in entries:
            try:
                owner_id = int(entry.get("owner", 0))
                # Recuperer le pseudo depuis le cache
                owner_name = card_system.get_username(owner_id)

                offers.append(TradeOffer(
                    id=int(entry.get("id", 0)),
                    owner_id=owner_id,
                    owner_name=owner_name,
                    category=entry.get("cat", ""),
                    name=entry.get("name", ""),
                    comment=entry.get("comment"),
                    timestamp=datetime.fromisoformat(entry.get("timestamp", datetime.now().isoformat()))
                ))
            except (ValueError, KeyError) as e:
                logger.warning(f"Offre invalide ignoree: {e}")
                continue

        return offers

    except Exception as e:
        logger.error(f"Erreur lors de la recuperation du tableau: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return []


@router.post("/board", status_code=status.HTTP_201_CREATED)
async def create_board_offer(
    offer: TradeOfferCreate,
    current_user: dict = Depends(get_current_user)
):
    """
    Depose une carte sur le tableau d'echanges.

    Args:
        offer: Details de l'offre (carte + commentaire)

    Returns:
        Succes de l'operation
    """
    user_id = current_user["user_id"]

    logger.info(f"Depot sur le tableau par {user_id}: {offer.category}/{offer.name}")

    try:
        # Verifier que l'utilisateur possede la carte
        has_card = card_system._user_has_card(user_id, offer.category, offer.name)
        if not has_card:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Vous ne possedez pas cette carte"
            )

        # Deposer sur le tableau
        success = await asyncio.to_thread(
            card_system.trading_manager.deposit_to_board,
            user_id,
            offer.category,
            offer.name,
            offer.comment
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erreur lors du depot sur le tableau"
            )

        return {"message": "Carte deposee sur le tableau d'echanges", "success": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors du depot: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors du depot sur le tableau"
        )


@router.delete("/board/{offer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def withdraw_board_offer(
    offer_id: int,
    current_user: dict = Depends(get_current_user)
):
    """
    Retire une offre du tableau d'echanges.
    Seul le proprietaire de l'offre peut la retirer.

    Args:
        offer_id: ID de l'offre a retirer
    """
    user_id = current_user["user_id"]

    logger.info(f"Retrait de l'offre {offer_id} par {user_id}")

    try:
        # Verifier que l'offre appartient a l'utilisateur
        entry = await asyncio.to_thread(
            card_system.storage.get_exchange_entry,
            offer_id
        )

        if not entry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Offre non trouvee"
            )

        if int(entry.get("owner", 0)) != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vous ne pouvez retirer que vos propres offres"
            )

        # Retirer du tableau et rendre la carte
        success = await asyncio.to_thread(
            card_system.trading_manager.withdraw_from_board,
            offer_id,
            user_id
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erreur lors du retrait"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors du retrait: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors du retrait de l'offre"
        )


@router.post("/board/{offer_id}/accept")
async def accept_board_offer(
    offer_id: int,
    proposal: TradeProposal,
    current_user: dict = Depends(get_current_user)
):
    """
    Accepte une offre du tableau en proposant des cartes en echange.
    Ceci cree une demande qui doit etre confirmee par le proprietaire de l'offre.

    Args:
        offer_id: ID de l'offre a accepter
        proposal: Cartes proposees en echange

    Returns:
        Details de l'echange en attente
    """
    user_id = current_user["user_id"]

    logger.info(f"Proposition d'echange par {user_id} pour l'offre {offer_id}")

    try:
        # Convertir les cartes proposees en tuples
        offered_cards = [(c.category, c.name) for c in proposal.offered_cards]

        # Verifier la proposition
        result = await asyncio.to_thread(
            card_system.trading_manager.initiate_board_trade,
            user_id,
            offer_id,
            offered_cards
        )

        if not result:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Proposition invalide. Verifiez que vous possedez les cartes proposees."
            )

        owner_id, board_cat, board_name = result

        return {
            "message": "Proposition envoyee. En attente de confirmation du proprietaire.",
            "offer_id": offer_id,
            "board_card": {"category": board_cat, "name": board_name},
            "offered_cards": [{"category": c.category, "name": c.name} for c in proposal.offered_cards],
            "owner_id": owner_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors de l'acceptation: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la proposition d'echange"
        )


@router.get("/history", response_model=List[TradeHistory])
async def get_trade_history(current_user: dict = Depends(get_current_user)):
    """
    Recupere l'historique des echanges de l'utilisateur.

    Returns:
        Liste des echanges passes
    """
    user_id = current_user["user_id"]

    logger.info(f"Recuperation de l'historique pour {user_id}")

    # TODO: Implementer quand le logging manager sera connecte
    return []


@router.get("/weekly-limit")
async def get_weekly_trade_limit(current_user: dict = Depends(get_current_user)):
    """
    Recupere le nombre d'echanges restants pour cette semaine.

    Returns:
        {remaining: int, limit: int, can_trade: bool}
    """
    user_id = current_user["user_id"]

    logger.info(f"Verification limite d'echanges pour {user_id}")

    try:
        # Utiliser notre methode existante
        exchanges_used = card_system._get_user_weekly_exchange_count(user_id)

        limit = 3  # WEEKLY_EXCHANGE_LIMIT du bot
        remaining = limit - exchanges_used

        return {
            "used": exchanges_used,
            "remaining": max(0, remaining),
            "limit": limit,
            "can_trade": remaining > 0
        }

    except Exception as e:
        logger.error(f"Erreur: {e}")
        return {
            "used": 0,
            "remaining": 3,
            "limit": 3,
            "can_trade": True
        }


@router.post("/direct")
async def create_direct_trade(
    trade_request: DirectTradeRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Cree une demande d'echange direct entre deux utilisateurs.

    Note: Les echanges directs ne sont pas encore implementes sur le site web.
    Utilisez le bot Discord pour les echanges directs.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Les echanges directs ne sont disponibles que via le bot Discord"
    )


@router.post("/vault/exchange")
async def exchange_vaults(
    request: VaultTradeRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Echange complet des vaults entre deux utilisateurs.

    Note: Les echanges de vault ne sont pas encore implementes sur le site web.
    Utilisez le bot Discord pour echanger vos vaults.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="L'echange de vaults n'est disponible que via le bot Discord"
    )
