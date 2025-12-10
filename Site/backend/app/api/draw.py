"""
Routes pour les tirages de cartes (journalier, bonus et sacrificiel).
- Tirage journalier: 3 cartes par jour
- Tirage bonus: 3 cartes (si bonus disponibles)
- Tirage sacrificiel: sacrifier 5 cartes pour en obtenir 3 nouvelles
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
import logging
import asyncio

from ..core.dependencies import get_current_user
from ..models.card import Card, CardPair
from ..services.cards_service import card_system

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/status")
async def get_draw_status(current_user: dict = Depends(get_current_user)):
    """
    Recupere le statut complet des tirages pour l'utilisateur.

    Returns:
        {
            can_daily_draw: bool,
            can_sacrificial_draw: bool,
            bonus_available: int,
            sacrificial_cards: List[{category, name}] - cartes eligibles
        }
    """
    user_id = current_user["user_id"]

    logger.info(f"Verification du statut des tirages pour l'utilisateur {user_id}")

    try:
        # Verifier tirage journalier
        can_daily = await asyncio.to_thread(
            card_system.drawing_manager.can_perform_daily_draw,
            user_id,
            check_only=True
        )

        # Verifier tirage sacrificiel (pas de parametre check_only)
        can_sacrificial = await asyncio.to_thread(
            card_system.drawing_manager.can_perform_sacrificial_draw,
            user_id
        )

        # Recuperer les bonus disponibles
        bonus_count = await asyncio.to_thread(
            card_system.get_user_bonus_count,
            user_id
        )

        # Recuperer les cartes eligibles au sacrifice (non-Full)
        collection_data = await card_system.get_user_collection(user_id)
        eligible_cards = [
            {"category": card["category"], "name": card["name"]}
            for card in collection_data["cards"]
            if not card.get("is_full", False)
        ]

        return {
            "can_daily_draw": can_daily,
            "can_sacrificial_draw": can_sacrificial and len(eligible_cards) >= 5,
            "bonus_available": bonus_count,
            "sacrificial_cards": eligible_cards,
            "total_cards": collection_data["total_cards"]
        }

    except Exception as e:
        logger.error(f"Erreur lors de la verification du statut: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la verification du statut des tirages"
        )


@router.get("/daily/status")
async def get_daily_draw_status(current_user: dict = Depends(get_current_user)):
    """
    Verifie si l'utilisateur peut effectuer son tirage journalier.

    Returns:
        {can_draw: bool, message: str}
    """
    user_id = current_user["user_id"]

    try:
        can_draw = await asyncio.to_thread(
            card_system.drawing_manager.can_perform_daily_draw,
            user_id,
            check_only=True
        )

        if can_draw:
            return {
                "can_draw": True,
                "message": "Tirage journalier disponible!"
            }
        else:
            return {
                "can_draw": False,
                "message": "Vous avez deja effectue votre tirage journalier aujourd'hui. Revenez demain!"
            }

    except Exception as e:
        logger.error(f"Erreur lors de la verification du tirage journalier: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la verification du tirage"
        )


@router.post("/daily", response_model=List[Card])
async def perform_daily_draw(current_user: dict = Depends(get_current_user)):
    """
    Effectue le tirage journalier de l'utilisateur (3 cartes).

    Returns:
        Liste des 3 cartes tirees

    Raises:
        HTTPException 403: Si le tirage journalier a deja ete effectue aujourd'hui
    """
    user_id = current_user["user_id"]

    logger.info(f"Tirage journalier demande par l'utilisateur {user_id}")

    try:
        # Reserver atomiquement le tirage
        can_draw = await asyncio.to_thread(
            card_system.drawing_manager.reserve_daily_draw,
            user_id
        )

        if not can_draw:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vous avez deja effectue votre tirage journalier aujourd'hui"
            )

        # Tirer 3 cartes (comme le bot Discord)
        drawn_cards = await asyncio.to_thread(
            card_system.drawing_manager.draw_cards,
            3
        )

        if not drawn_cards or len(drawn_cards) < 3:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erreur lors du tirage de cartes"
            )

        result_cards = []
        for category, name in drawn_cards:
            # Ajouter la carte a la collection
            await asyncio.to_thread(
                card_system._add_card_to_user,
                user_id,
                category,
                name
            )

            # Trouver le file_id
            file_id = None
            for card in card_system.cards_by_category.get(category, []):
                if card["name"] == name:
                    file_id = card.get("file_id")
                    break

            result_cards.append(Card(
                category=category,
                name=name,
                file_id=file_id,
                is_full=False,
                rarity_weight=0
            ))

        logger.info(f"Tirage journalier reussi pour {user_id}: {len(result_cards)} cartes")

        return result_cards

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors du tirage journalier: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors du tirage journalier"
        )


@router.post("/bonus", response_model=List[Card])
async def perform_bonus_draw(current_user: dict = Depends(get_current_user)):
    """
    Effectue un tirage bonus (3 cartes).

    Returns:
        Liste des 3 cartes tirees

    Raises:
        HTTPException 403: Si aucun bonus n'est disponible
    """
    user_id = current_user["user_id"]

    logger.info(f"Tirage bonus demande par l'utilisateur {user_id}")

    try:
        # Verifier les bonus disponibles
        bonus_count = await asyncio.to_thread(
            card_system.storage.get_user_bonus_count,
            user_id
        )

        if bonus_count <= 0:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vous n'avez aucun tirage bonus disponible"
            )

        # Consommer un bonus
        await asyncio.to_thread(
            card_system.storage.consume_user_bonus,
            user_id
        )

        # Tirer 3 cartes
        drawn_cards = await asyncio.to_thread(
            card_system.drawing_manager.draw_cards,
            3
        )

        if not drawn_cards or len(drawn_cards) < 3:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erreur lors du tirage de cartes"
            )

        result_cards = []
        for category, name in drawn_cards:
            # Ajouter la carte a la collection
            await asyncio.to_thread(
                card_system._add_card_to_user,
                user_id,
                category,
                name
            )

            # Trouver le file_id
            file_id = None
            for card in card_system.cards_by_category.get(category, []):
                if card["name"] == name:
                    file_id = card.get("file_id")
                    break

            result_cards.append(Card(
                category=category,
                name=name,
                file_id=file_id,
                is_full=False,
                rarity_weight=0
            ))

        logger.info(f"Tirage bonus reussi pour {user_id}: {len(result_cards)} cartes")

        return result_cards

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors du tirage bonus: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors du tirage bonus"
        )


@router.get("/sacrificial/status")
async def get_sacrificial_draw_status(current_user: dict = Depends(get_current_user)):
    """
    Verifie si l'utilisateur peut effectuer son tirage sacrificiel.

    Returns:
        {can_draw: bool, message: str, eligible_count: int}
    """
    user_id = current_user["user_id"]

    try:
        can_draw = await asyncio.to_thread(
            card_system.drawing_manager.can_perform_sacrificial_draw,
            user_id
        )

        # Compter les cartes eligibles (non-Full)
        collection_data = await card_system.get_user_collection(user_id)
        eligible_count = sum(
            1 for card in collection_data["cards"]
            if not card.get("is_full", False)
        )

        if not can_draw:
            return {
                "can_draw": False,
                "message": "Vous avez deja effectue votre tirage sacrificiel aujourd'hui.",
                "eligible_count": eligible_count
            }
        elif eligible_count < 5:
            return {
                "can_draw": False,
                "message": f"Vous devez avoir au moins 5 cartes non-Full. Vous en avez {eligible_count}.",
                "eligible_count": eligible_count
            }
        else:
            return {
                "can_draw": True,
                "message": "Tirage sacrificiel disponible!",
                "eligible_count": eligible_count
            }

    except Exception as e:
        logger.error(f"Erreur lors de la verification du tirage sacrificiel: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la verification du tirage"
        )


@router.get("/sacrificial/preview", response_model=List[CardPair])
async def get_sacrificial_preview(current_user: dict = Depends(get_current_user)):
    """
    Recupere les 5 cartes qui seront sacrifiees pour le tirage.
    Cette selection est deterministe et reste la meme toute la journee.

    Returns:
        Liste de 5 cartes qui seront sacrifiees
    """
    user_id = current_user["user_id"]

    try:
        # Recuperer les cartes avec repetitions (comme le bot)
        user_cards_tuples = await asyncio.to_thread(
            card_system._get_user_cards_internal,
            user_id
        )

        # Filtrer les cartes non-Full
        eligible_tuples = [
            (cat, name) for cat, name in user_cards_tuples
            if "(Full)" not in name
        ]

        if len(eligible_tuples) < 5:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Vous devez avoir au moins 5 cartes non-Full. Vous en avez {len(eligible_tuples)}."
            )

        # Selection deterministe des 5 cartes (avec doublons)
        selected_cards = await asyncio.to_thread(
            card_system.drawing_manager.select_daily_sacrificial_cards,
            user_id,
            eligible_tuples
        )

        return [
            CardPair(category=cat, name=name)
            for cat, name in selected_cards
        ]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors de l'apercu du tirage sacrificiel: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de l'apercu du tirage sacrificiel"
        )


@router.post("/sacrificial", response_model=List[Card])
async def perform_sacrificial_draw(current_user: dict = Depends(get_current_user)):
    """
    Effectue le tirage sacrificiel: sacrifice 5 cartes pour en obtenir 3 nouvelles.

    Returns:
        Liste des 3 cartes tirees

    Raises:
        HTTPException 403: Si le tirage sacrificiel a deja ete effectue
        HTTPException 400: Si l'utilisateur n'a pas assez de cartes
    """
    user_id = current_user["user_id"]

    logger.info(f"Tirage sacrificiel demande par l'utilisateur {user_id}")

    try:
        # 1. Verifier si le tirage est disponible
        can_draw = await asyncio.to_thread(
            card_system.drawing_manager.can_perform_sacrificial_draw,
            user_id
        )

        if not can_draw:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vous avez deja effectue votre tirage sacrificiel aujourd'hui"
            )

        # 2. Recuperer les cartes eligibles (non-Full) avec repetitions
        # Le bot utilise une liste avec doublons (si on a 3x la meme carte, elle apparait 3 fois)
        user_cards_tuples = await asyncio.to_thread(
            card_system._get_user_cards_internal,
            user_id
        )

        # Filtrer les cartes non-Full
        eligible_tuples = [
            (cat, name) for cat, name in user_cards_tuples
            if "(Full)" not in name
        ]

        if len(eligible_tuples) < 5:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Vous devez avoir au moins 5 cartes non-Full. Vous en avez {len(eligible_tuples)}."
            )

        # 3. Obtenir les 5 cartes a sacrifier (selection deterministe)
        # Cette fonction attend une liste avec doublons
        cards_to_sacrifice = await asyncio.to_thread(
            card_system.drawing_manager.select_daily_sacrificial_cards,
            user_id,
            eligible_tuples
        )

        logger.info(f"Cartes a sacrifier pour {user_id}: {cards_to_sacrifice}")

        # 4. Retirer les 5 cartes de la collection
        for category, name in cards_to_sacrifice:
            success = await asyncio.to_thread(
                card_system._remove_card_from_user,
                user_id,
                category,
                name
            )
            if not success:
                logger.error(f"Echec du retrait de {category}/{name} pour {user_id}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Erreur lors du retrait des cartes sacrifiees"
                )

        logger.info(f"Cartes sacrifiees retirees pour {user_id}")

        # 5. Tirer 3 nouvelles cartes (pas 5!)
        new_cards = await asyncio.to_thread(
            card_system.drawing_manager.draw_cards,
            3
        )

        if not new_cards or len(new_cards) < 3:
            logger.error(f"Echec du tirage de nouvelles cartes pour {user_id}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erreur lors du tirage de nouvelles cartes"
            )

        logger.info(f"Nouvelles cartes tirees pour {user_id}: {new_cards}")

        # 6. Enregistrer le tirage sacrificiel
        await asyncio.to_thread(
            card_system.drawing_manager.record_sacrificial_draw,
            user_id
        )

        # 7. Ajouter les 3 nouvelles cartes
        result_cards = []
        for category, name in new_cards:
            await asyncio.to_thread(
                card_system._add_card_to_user,
                user_id,
                category,
                name
            )

            # Trouver le file_id
            file_id = None
            for card in card_system.cards_by_category.get(category, []):
                if card["name"] == name:
                    file_id = card.get("file_id")
                    break

            result_cards.append(Card(
                category=category,
                name=name,
                file_id=file_id,
                is_full=False,
                rarity_weight=0
            ))

        logger.info(f"Tirage sacrificiel reussi pour {user_id}: 5 cartes sacrifiees, 3 obtenues")

        return result_cards

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors du tirage sacrificiel: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors du tirage sacrificiel"
        )
