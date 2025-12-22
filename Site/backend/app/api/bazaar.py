"""
Routes pour le systeme Bazaar - Echanges de cartes.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Dict, Any, List, Optional
import logging
import asyncio
import uuid
from datetime import datetime, timedelta

from ..core.dependencies import get_current_user
from ..models.bazaar import (
    TradeRequest, TradeRequestCreate, TradeRequestStatus,
    BazaarSearchResult, CardAvailability, UserCardForTrade,
    UserTradeRequests, CardInfo
)
from ..services.cards_service import card_system

router = APIRouter()
logger = logging.getLogger(__name__)

# Nom de la sheet pour les demandes d'echange
TRADE_REQUESTS_SHEET = "TradeRequests"


@router.get("/ping")
async def ping_bazaar():
    """Endpoint simple pour tester si le router fonctionne."""
    return {"status": "ok", "message": "Bazaar router is working"}


def _get_or_create_trade_requests_sheet():
    """Recupere ou cree la sheet des demandes d'echange."""
    try:
        return card_system.storage.spreadsheet.worksheet(TRADE_REQUESTS_SHEET)
    except Exception:
        # Creer la sheet si elle n'existe pas
        sheet = card_system.storage.spreadsheet.add_worksheet(
            title=TRADE_REQUESTS_SHEET, rows="1000", cols="15"
        )
        # Ajouter l'en-tete (14 colonnes)
        # Colonne 14 = notified_at pour le systeme de notifications Discord
        sheet.append_row([
            "id", "requester_id", "requester_name", "target_id", "target_name",
            "offered_category", "offered_name", "requested_category", "requested_name",
            "status", "created_at", "expires_at", "resolved_at", "notified_at"
        ])
        return sheet


def _get_discovered_cards() -> set:
    """Retourne l'ensemble des cartes decouvertes (category, name)."""
    try:
        discoveries = card_system.storage.sheet_discoveries.get_all_values()[1:]
        # Normaliser les noms (strip espaces)
        return {(row[0].strip(), row[1].strip()) for row in discoveries if len(row) >= 2 and row[0] and row[1]}
    except Exception as e:
        logger.error(f"Erreur lors de la lecture des decouvertes: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return set()


def _get_all_owned_cards() -> Dict[tuple, List[dict]]:
    """
    Retourne toutes les cartes possedees avec leurs proprietaires.
    Format: {(category, name): [{"user_id": str, "count": int}, ...]}
    """
    result = {}

    try:
        cards_cache = card_system.storage.get_cards_cache()
        if not cards_cache:
            logger.warning("[BAZAAR] Cache des cartes vide ou None")
            return result

        logger.info(f"[BAZAAR] Cache des cartes: {len(cards_cache)} lignes")

        for row in cards_cache[1:]:  # Skip header
            if len(row) < 3:
                continue

            # Normaliser les noms (strip espaces)
            category = row[0].strip() if row[0] else ""
            name = row[1].strip() if row[1] else ""

            if not category or not name:
                continue

            key = (category, name)

            owners = []
            for cell in row[2:]:
                if not cell:
                    continue
                try:
                    uid, count = cell.split(":", 1)
                    owners.append({
                        "user_id": uid.strip(),
                        "count": int(count)
                    })
                except (ValueError, IndexError):
                    continue

            if owners:
                result[key] = owners

    except Exception as e:
        logger.error(f"Erreur lors de la lecture des cartes: {e}")
        import traceback
        logger.error(traceback.format_exc())

    return result


def _get_user_card_count(user_id: int, category: str, name: str) -> int:
    """Retourne le nombre d'exemplaires d'une carte pour un utilisateur."""
    try:
        cards_cache = card_system.storage.get_cards_cache()
        if not cards_cache:
            return 0

        for row in cards_cache:
            if len(row) >= 2 and row[0] == category and row[1] == name:
                for cell in row[2:]:
                    if not cell:
                        continue
                    try:
                        uid, count = cell.split(":", 1)
                        if int(uid.strip()) == user_id:
                            return int(count)
                    except (ValueError, IndexError):
                        continue
        return 0
    except Exception as e:
        logger.error(f"Erreur _get_user_card_count: {e}")
        return 0


def _transfer_card(from_user_id: int, to_user_id: int, category: str, name: str) -> bool:
    """Transfere une carte d'un utilisateur a un autre."""
    try:
        storage = card_system.storage

        with storage._cards_lock:
            cards_cache = storage.get_cards_cache()
            if not cards_cache:
                return False

            for i, row in enumerate(cards_cache):
                if len(row) >= 2 and row[0] == category and row[1] == name:
                    original_len = len(row)

                    # 1. Retirer la carte du donneur
                    from_found = False
                    for j, cell in enumerate(row[2:], start=2):
                        if not cell:
                            continue
                        try:
                            uid, count = cell.split(":", 1)
                            if int(uid.strip()) == from_user_id:
                                count = int(count)
                                if count <= 0:
                                    return False
                                if count > 1:
                                    row[j] = f"{from_user_id}:{count-1}"
                                else:
                                    row[j] = ""
                                from_found = True
                                break
                        except (ValueError, IndexError):
                            continue

                    if not from_found:
                        return False

                    # 2. Ajouter la carte au receveur
                    to_found = False
                    for j, cell in enumerate(row[2:], start=2):
                        if not cell:
                            continue
                        try:
                            uid, count = cell.split(":", 1)
                            if int(uid.strip()) == to_user_id:
                                new_count = int(count) + 1
                                row[j] = f"{to_user_id}:{new_count}"
                                to_found = True
                                break
                        except (ValueError, IndexError):
                            continue

                    if not to_found:
                        # Ajouter nouvelle entree pour le receveur
                        row.append(f"{to_user_id}:1")

                    # 3. Nettoyer et sauvegarder
                    header = row[:2]
                    data = [c for c in row[2:] if c and c.strip()]
                    cleaned_row = header + data
                    pad = max(original_len, len(cleaned_row)) - len(cleaned_row)
                    cleaned_row += [""] * pad

                    storage.sheet_cards.update(f"A{i+1}", [cleaned_row])
                    storage.refresh_cards_cache()
                    return True

            return False

    except Exception as e:
        logger.error(f"Erreur _transfer_card: {e}")
        return False


@router.get("/debug")
async def debug_bazaar(
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Endpoint de debug pour comprendre pourquoi la recherche ne trouve pas de cartes.
    """
    try:
        discovered_cards = await asyncio.to_thread(_get_discovered_cards)
        all_owned = await asyncio.to_thread(_get_all_owned_cards)

        # Exemples de cartes decouvertes
        discovered_sample = list(discovered_cards)[:10]

        # Exemples de cartes possedees
        owned_sample = [(k, v) for k, v in list(all_owned.items())[:10]]

        # Verifier les correspondances
        matches = []
        non_matches_owned = []

        for (cat, name), owners in list(all_owned.items())[:20]:
            if (cat, name) in discovered_cards:
                matches.append({"category": cat, "name": name, "owners_count": len(owners)})
            else:
                non_matches_owned.append({"category": cat, "name": name, "owners_count": len(owners)})

        return {
            "discovered_count": len(discovered_cards),
            "owned_count": len(all_owned),
            "matches_count": len(matches),
            "discovered_sample": [{"category": c, "name": n} for c, n in discovered_sample],
            "owned_sample": [{"category": k[0], "name": k[1], "owners": v} for k, v in owned_sample],
            "matches": matches[:10],
            "non_matches_owned": non_matches_owned[:10],
            "current_user_id": current_user["user_id"]
        }

    except Exception as e:
        logger.error(f"Erreur debug: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {"error": str(e), "traceback": traceback.format_exc()}


@router.get("/search", response_model=BazaarSearchResult)
async def search_bazaar(
    query: Optional[str] = Query(None, description="Recherche textuelle"),
    category: Optional[str] = Query(None, description="Filtrer par categorie"),
    include_non_duplicates: bool = Query(False, description="Inclure les cartes non-doublons"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user)
) -> BazaarSearchResult:
    """
    Recherche des cartes disponibles dans le Bazaar.

    Seules les cartes decouvertes sont visibles.
    Par defaut, seules les cartes en doublon sont affichees.
    """
    try:
        current_user_id = current_user["user_id"]

        # Recuperer les cartes decouvertes
        discovered_cards = await asyncio.to_thread(_get_discovered_cards)
        logger.info(f"[BAZAAR] Cartes decouvertes: {len(discovered_cards)}")

        # Recuperer toutes les cartes possedees
        all_owned = await asyncio.to_thread(_get_all_owned_cards)
        logger.info(f"[BAZAAR] Cartes possedees: {len(all_owned)}")

        # Filtrer et construire les resultats
        results = []
        skipped_not_discovered = 0
        skipped_no_owners = 0
        skipped_category = 0
        skipped_query = 0

        for (cat, name), owners in all_owned.items():
            # Verifier si la carte est decouverte
            if (cat, name) not in discovered_cards:
                skipped_not_discovered += 1
                continue

            # Filtre par categorie
            if category and cat != category:
                skipped_category += 1
                continue

            # Filtre par recherche textuelle
            if query:
                query_lower = query.lower()
                if query_lower not in name.lower() and query_lower not in cat.lower():
                    skipped_query += 1
                    continue

            # Calculer la disponibilite
            available_owners = []
            total_available = 0

            for owner in owners:
                owner_id = owner["user_id"]
                count = owner["count"]

                # Ne pas afficher ses propres cartes
                if int(owner_id) == current_user_id:
                    continue

                # Calculer combien sont disponibles a l'echange
                if include_non_duplicates:
                    available = count  # Toutes les cartes
                else:
                    available = count - 1  # Seulement les doublons

                if available > 0:
                    # Recuperer le username depuis le cache (si disponible)
                    username = card_system.get_username(int(owner_id)) or f"User_{owner_id}"

                    available_owners.append({
                        "user_id": owner_id,
                        "username": username,
                        "count": count,
                        "available": available
                    })
                    total_available += available

            # Ajouter seulement si des cartes sont disponibles
            if available_owners:
                # Recuperer le file_id de la carte
                file_id = None
                for card in card_system.cards_by_category.get(cat, []):
                    if card["name"] == name:
                        file_id = card.get("file_id")
                        break

                results.append(CardAvailability(
                    category=cat,
                    name=name,
                    file_id=file_id,
                    owners=available_owners,
                    total_available=total_available
                ))
            else:
                skipped_no_owners += 1

        logger.info(f"[BAZAAR] Resultats: {len(results)}, non-decouverts: {skipped_not_discovered}, sans proprio dispo: {skipped_no_owners}")

        # Pagination
        total = len(results)
        total_pages = (total + per_page - 1) // per_page
        start = (page - 1) * per_page
        end = start + per_page
        paginated_results = results[start:end]

        return BazaarSearchResult(
            cards=paginated_results,
            total=total,
            page=page,
            per_page=per_page,
            total_pages=total_pages
        )

    except Exception as e:
        logger.error(f"Erreur lors de la recherche Bazaar: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la recherche"
        )


@router.post("/propose", response_model=TradeRequest)
async def propose_trade(
    request: TradeRequestCreate,
    current_user: dict = Depends(get_current_user)
) -> TradeRequest:
    """
    Propose un echange a un autre utilisateur.

    L'initiateur offre une de ses cartes en echange d'une carte du destinataire.
    La demande expire apres 24h.
    """
    try:
        requester_id = current_user["user_id"]
        requester_id_str = current_user["user_id_str"]
        requester_name = current_user.get("global_name") or current_user["username"]

        target_id = int(request.target_id)
        target_id_str = request.target_id

        # Verifications
        if requester_id == target_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Vous ne pouvez pas echanger avec vous-meme"
            )

        # Verifier que l'initiateur possede la carte offerte
        offered_count = await asyncio.to_thread(
            _get_user_card_count,
            requester_id, request.offered_category, request.offered_name
        )
        if offered_count < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Vous ne possedez pas cette carte"
            )

        # Verifier que le destinataire possede la carte demandee
        requested_count = await asyncio.to_thread(
            _get_user_card_count,
            target_id, request.requested_category, request.requested_name
        )
        if requested_count < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Le destinataire ne possede pas cette carte"
            )

        # Recuperer le nom du destinataire
        target_name = card_system.get_username(target_id) or f"User_{target_id}"

        # Creer la demande
        trade_id = f"trade_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()
        expires_at = now + timedelta(hours=24)

        trade_request = TradeRequest(
            id=trade_id,
            requester_id=requester_id_str,
            requester_name=requester_name,
            target_id=target_id_str,
            target_name=target_name,
            offered_card=CardInfo(
                category=request.offered_category,
                name=request.offered_name
            ),
            requested_card=CardInfo(
                category=request.requested_category,
                name=request.requested_name
            ),
            status=TradeRequestStatus.PENDING,
            created_at=now,
            expires_at=expires_at
        )

        # Sauvegarder dans la sheet
        sheet = await asyncio.to_thread(_get_or_create_trade_requests_sheet)
        await asyncio.to_thread(
            sheet.append_row,
            [
                trade_id,
                requester_id_str,
                requester_name,
                target_id_str,
                target_name,
                request.offered_category,
                request.offered_name,
                request.requested_category,
                request.requested_name,
                TradeRequestStatus.PENDING.value,
                now.isoformat(),
                expires_at.isoformat(),
                ""
            ]
        )

        logger.info(f"Nouvelle demande d'echange creee: {trade_id}")

        # TODO: Envoyer notification Discord DM au destinataire

        return trade_request

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors de la creation de la demande: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la creation de la demande"
        )


@router.get("/requests", response_model=UserTradeRequests)
async def get_my_trade_requests(
    current_user: dict = Depends(get_current_user)
) -> UserTradeRequests:
    """
    Recupere les demandes d'echange de l'utilisateur connecte.

    Retourne les demandes recues et envoyees qui sont encore en attente.
    """
    try:
        user_id_str = current_user["user_id_str"]

        sheet = await asyncio.to_thread(_get_or_create_trade_requests_sheet)

        # Gerer le cas ou la sheet est vide ou n'a que des en-tetes
        try:
            records = await asyncio.to_thread(sheet.get_all_records)
        except Exception as e:
            logger.warning(f"Sheet TradeRequests vide ou erreur: {e}")
            records = []

        received = []
        sent = []
        now = datetime.utcnow()

        for record in records:
            # Ignorer les demandes non-pending
            if record.get("status") != TradeRequestStatus.PENDING.value:
                continue

            # Verifier l'expiration
            try:
                expires_at = datetime.fromisoformat(record.get("expires_at", ""))
                if expires_at < now:
                    continue  # Expiree
            except (ValueError, TypeError):
                continue

            trade_request = TradeRequest(
                id=record.get("id", ""),
                requester_id=str(record.get("requester_id", "")),
                requester_name=record.get("requester_name", ""),
                target_id=str(record.get("target_id", "")),
                target_name=record.get("target_name", ""),
                offered_card=CardInfo(
                    category=record.get("offered_category", ""),
                    name=record.get("offered_name", "")
                ),
                requested_card=CardInfo(
                    category=record.get("requested_category", ""),
                    name=record.get("requested_name", "")
                ),
                status=TradeRequestStatus(record.get("status", "pending")),
                created_at=datetime.fromisoformat(record.get("created_at", now.isoformat())),
                expires_at=expires_at
            )

            # Classer par type
            if str(record.get("target_id")) == user_id_str:
                received.append(trade_request)
            elif str(record.get("requester_id")) == user_id_str:
                sent.append(trade_request)

        return UserTradeRequests(received=received, sent=sent)

    except Exception as e:
        logger.error(f"Erreur lors de la recuperation des demandes: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la recuperation des demandes"
        )


@router.post("/accept/{trade_id}")
async def accept_trade(
    trade_id: str,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Accepte une demande d'echange.

    Effectue le transfert des cartes entre les deux utilisateurs.
    """
    try:
        user_id = current_user["user_id"]
        user_id_str = current_user["user_id_str"]

        sheet = await asyncio.to_thread(_get_or_create_trade_requests_sheet)

        try:
            records = await asyncio.to_thread(sheet.get_all_records)
        except Exception as e:
            logger.warning(f"Erreur lecture TradeRequests: {e}")
            records = []

        # Trouver la demande
        trade_record = None
        row_index = None
        for i, record in enumerate(records):
            if record.get("id") == trade_id:
                trade_record = record
                row_index = i + 2  # +2 car en-tete + index 0-based
                break

        if not trade_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Demande non trouvee"
            )

        # Verifier que l'utilisateur est le destinataire
        if str(trade_record.get("target_id")) != user_id_str:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vous n'etes pas le destinataire de cette demande"
            )

        # Verifier le statut
        if trade_record.get("status") != TradeRequestStatus.PENDING.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cette demande n'est plus en attente"
            )

        # Verifier l'expiration
        try:
            expires_at = datetime.fromisoformat(trade_record.get("expires_at", ""))
            if expires_at < datetime.utcnow():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cette demande a expire"
                )
        except (ValueError, TypeError):
            pass

        requester_id = int(trade_record.get("requester_id"))
        target_id = user_id

        offered_cat = trade_record.get("offered_category")
        offered_name = trade_record.get("offered_name")
        requested_cat = trade_record.get("requested_category")
        requested_name = trade_record.get("requested_name")

        # Verifier que les deux parties possedent toujours les cartes
        requester_has = await asyncio.to_thread(
            _get_user_card_count, requester_id, offered_cat, offered_name
        )
        target_has = await asyncio.to_thread(
            _get_user_card_count, target_id, requested_cat, requested_name
        )

        if requester_has < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="L'initiateur ne possede plus la carte offerte"
            )

        if target_has < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Vous ne possedez plus la carte demandee"
            )

        # Effectuer le transfert
        # 1. Carte offerte: requester -> target
        success1 = await asyncio.to_thread(
            _transfer_card, requester_id, target_id, offered_cat, offered_name
        )

        if not success1:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erreur lors du transfert de la carte offerte"
            )

        # 2. Carte demandee: target -> requester
        success2 = await asyncio.to_thread(
            _transfer_card, target_id, requester_id, requested_cat, requested_name
        )

        if not success2:
            # Rollback - remettre la premiere carte
            await asyncio.to_thread(
                _transfer_card, target_id, requester_id, offered_cat, offered_name
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erreur lors du transfert de la carte demandee"
            )

        # Mettre a jour le statut
        now = datetime.utcnow()
        await asyncio.to_thread(
            sheet.update_cell, row_index, 10, TradeRequestStatus.ACCEPTED.value
        )
        await asyncio.to_thread(
            sheet.update_cell, row_index, 13, now.isoformat()
        )

        logger.info(f"Echange {trade_id} accepte et complete")

        # TODO: Envoyer notification Discord DM a l'initiateur

        return {
            "success": True,
            "message": "Echange effectue avec succes",
            "trade_id": trade_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors de l'acceptation de l'echange: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de l'acceptation de l'echange"
        )


@router.post("/decline/{trade_id}")
async def decline_trade(
    trade_id: str,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """Refuse une demande d'echange."""
    try:
        user_id_str = current_user["user_id_str"]

        sheet = await asyncio.to_thread(_get_or_create_trade_requests_sheet)

        try:
            records = await asyncio.to_thread(sheet.get_all_records)
        except Exception as e:
            logger.warning(f"Erreur lecture TradeRequests: {e}")
            records = []

        # Trouver la demande
        row_index = None
        for i, record in enumerate(records):
            if record.get("id") == trade_id:
                if str(record.get("target_id")) != user_id_str:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Vous n'etes pas le destinataire de cette demande"
                    )
                if record.get("status") != TradeRequestStatus.PENDING.value:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Cette demande n'est plus en attente"
                    )
                row_index = i + 2
                break

        if not row_index:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Demande non trouvee"
            )

        # Mettre a jour le statut
        now = datetime.utcnow()
        await asyncio.to_thread(
            sheet.update_cell, row_index, 10, TradeRequestStatus.DECLINED.value
        )
        await asyncio.to_thread(
            sheet.update_cell, row_index, 13, now.isoformat()
        )

        logger.info(f"Echange {trade_id} refuse")

        # TODO: Envoyer notification Discord DM a l'initiateur

        return {
            "success": True,
            "message": "Demande refusee",
            "trade_id": trade_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors du refus de l'echange: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors du refus de l'echange"
        )


@router.delete("/cancel/{trade_id}")
async def cancel_trade(
    trade_id: str,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """Annule une demande d'echange envoyee."""
    try:
        user_id_str = current_user["user_id_str"]

        sheet = await asyncio.to_thread(_get_or_create_trade_requests_sheet)

        try:
            records = await asyncio.to_thread(sheet.get_all_records)
        except Exception as e:
            logger.warning(f"Erreur lecture TradeRequests: {e}")
            records = []

        # Trouver la demande
        row_index = None
        for i, record in enumerate(records):
            if record.get("id") == trade_id:
                if str(record.get("requester_id")) != user_id_str:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Vous n'etes pas l'initiateur de cette demande"
                    )
                if record.get("status") != TradeRequestStatus.PENDING.value:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Cette demande n'est plus en attente"
                    )
                row_index = i + 2
                break

        if not row_index:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Demande non trouvee"
            )

        # Mettre a jour le statut
        now = datetime.utcnow()
        await asyncio.to_thread(
            sheet.update_cell, row_index, 10, TradeRequestStatus.CANCELLED.value
        )
        await asyncio.to_thread(
            sheet.update_cell, row_index, 13, now.isoformat()
        )

        logger.info(f"Echange {trade_id} annule")

        return {
            "success": True,
            "message": "Demande annulee",
            "trade_id": trade_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors de l'annulation de l'echange: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de l'annulation de l'echange"
        )


@router.get("/user/{user_id}/available")
async def get_user_available_cards(
    user_id: str,
    include_non_duplicates: bool = Query(False),
    current_user: dict = Depends(get_current_user)
) -> List[CardInfo]:
    """
    Recupere les cartes disponibles a l'echange d'un utilisateur specifique.

    Utile pour voir ce qu'on peut demander a un utilisateur.
    """
    try:
        target_user_id = int(user_id)

        # Recuperer les cartes decouvertes
        discovered_cards = await asyncio.to_thread(_get_discovered_cards)

        # Recuperer toutes les cartes possedees
        all_owned = await asyncio.to_thread(_get_all_owned_cards)

        available_cards = []

        for (cat, name), owners in all_owned.items():
            # Verifier si la carte est decouverte
            if (cat, name) not in discovered_cards:
                continue

            for owner in owners:
                if int(owner["user_id"]) == target_user_id:
                    count = owner["count"]
                    available = count if include_non_duplicates else count - 1

                    if available > 0:
                        # Recuperer le file_id
                        file_id = None
                        for card in card_system.cards_by_category.get(cat, []):
                            if card["name"] == name:
                                file_id = card.get("file_id")
                                break

                        available_cards.append(CardInfo(
                            category=cat,
                            name=name,
                            file_id=file_id
                        ))
                    break

        return available_cards

    except Exception as e:
        logger.error(f"Erreur lors de la recuperation des cartes disponibles: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la recuperation des cartes"
        )
