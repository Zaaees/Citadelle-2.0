"""
Routes de migration vers le systeme Bazaar.

Ces endpoints sont temporaires et doivent etre supprimes apres la migration.
"""

from fastapi import APIRouter, HTTPException, status
from typing import Dict, Any, List
import logging
import asyncio

from ..services.cards_service import card_system

router = APIRouter()
logger = logging.getLogger(__name__)


def _add_card_to_user_direct(user_id: int, category: str, name: str) -> bool:
    """
    Ajoute une carte a l'inventaire d'un utilisateur.
    Implementation directe sans passer par les managers.
    """
    try:
        storage = card_system.storage

        with storage._cards_lock:
            cards_cache = storage.get_cards_cache()
            if not cards_cache:
                return False

            # Chercher la carte
            for i, row in enumerate(cards_cache):
                if len(row) >= 2 and row[0] == category and row[1] == name:
                    original_len = len(row)

                    # Chercher si l'utilisateur a deja cette carte
                    for j, cell in enumerate(row[2:], start=2):
                        if not cell:
                            continue
                        try:
                            uid, count = cell.split(":", 1)
                            uid = uid.strip()
                            if int(uid) == user_id:
                                # Incrementer
                                new_count = int(count) + 1
                                row[j] = f"{user_id}:{new_count}"

                                # Nettoyer et mettre a jour
                                cleaned_row = _merge_cells(row)
                                pad = max(original_len, len(cleaned_row)) - len(cleaned_row)
                                cleaned_row += [""] * pad
                                storage.sheet_cards.update(f"A{i+1}", [cleaned_row])
                                storage.refresh_cards_cache()
                                return True
                        except (ValueError, IndexError):
                            continue

                    # Utilisateur pas trouve, ajouter une nouvelle entree
                    row.append(f"{user_id}:1")
                    cleaned_row = _merge_cells(row)
                    pad = max(original_len + 1, len(cleaned_row)) - len(cleaned_row)
                    cleaned_row += [""] * pad
                    storage.sheet_cards.update(f"A{i+1}", [cleaned_row])
                    storage.refresh_cards_cache()
                    return True

            # Carte non trouvee
            logger.error(f"Carte non trouvee: {category}/{name}")
            return False

    except Exception as e:
        logger.error(f"Erreur _add_card_to_user_direct: {e}")
        return False


def _merge_cells(row: list) -> list:
    """Nettoie une ligne en supprimant les cellules vides intermediaires."""
    if len(row) < 3:
        return row

    header = row[:2]
    data = [c for c in row[2:] if c and c.strip()]
    return header + data


@router.get("/preview")
async def preview_migration() -> Dict[str, Any]:
    """
    Previsualise les donnees a migrer sans effectuer de modifications.

    Returns:
        Donnees du tableau d'echange et du vault
    """
    try:
        result = {
            "exchange_board": [],
            "vault": [],
            "summary": {
                "exchange_cards_count": 0,
                "vault_cards_count": 0,
                "exchange_users": set(),
                "vault_users": set()
            }
        }

        # Tableau d'echange
        exchange_entries = await asyncio.to_thread(
            card_system.storage.get_exchange_entries
        )

        for entry in exchange_entries:
            result["exchange_board"].append({
                "id": entry.get("id"),
                "owner_id": entry.get("owner"),
                "category": entry.get("cat"),
                "name": entry.get("name"),
                "comment": entry.get("comment"),
                "timestamp": entry.get("timestamp")
            })
            result["summary"]["exchange_cards_count"] += 1
            result["summary"]["exchange_users"].add(str(entry.get("owner")))

        # Vault
        vault_data = await asyncio.to_thread(
            lambda: card_system.storage.sheet_vault.get_all_values()
        )

        for row in vault_data[1:]:  # Skip header
            if len(row) < 3:
                continue

            category = row[0]
            name = row[1]

            for cell in row[2:]:
                if not cell:
                    continue
                try:
                    uid, count = cell.split(":", 1)
                    uid = uid.strip()
                    count = int(count)

                    result["vault"].append({
                        "user_id": uid,
                        "category": category,
                        "name": name,
                        "count": count
                    })
                    result["summary"]["vault_cards_count"] += count
                    result["summary"]["vault_users"].add(uid)
                except (ValueError, IndexError):
                    continue

        # Convertir les sets en listes pour JSON
        result["summary"]["exchange_users"] = list(result["summary"]["exchange_users"])
        result["summary"]["vault_users"] = list(result["summary"]["vault_users"])

        return result

    except Exception as e:
        logger.error(f"Erreur lors de la previsualisation: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur: {str(e)}"
        )


@router.post("/execute")
async def execute_migration() -> Dict[str, Any]:
    """
    Execute la migration:
    1. Restaure les cartes du tableau d'echange aux proprietaires
    2. Restaure les cartes des coffres aux proprietaires
    3. Vide les sheets correspondantes

    ATTENTION: Cette operation est irreversible!

    Returns:
        Statistiques de migration
    """
    stats = {
        "exchange_board": {"restored": 0, "errors": 0, "users": []},
        "vault": {"restored": 0, "errors": 0, "users": []},
        "success": False
    }

    try:
        # Phase 1: Migrer le tableau d'echange
        logger.info("=== MIGRATION: Phase 1 - Tableau d'echange ===")

        exchange_entries = await asyncio.to_thread(
            card_system.storage.get_exchange_entries
        )

        exchange_users = set()

        for entry in exchange_entries:
            owner_id = entry.get("owner")
            category = entry.get("cat")
            name = entry.get("name")
            entry_id = entry.get("id")

            if not owner_id or not category or not name:
                logger.warning(f"Entree invalide ignoree: {entry}")
                stats["exchange_board"]["errors"] += 1
                continue

            owner_id = int(owner_id)

            # Ajouter la carte au proprietaire
            success = await asyncio.to_thread(
                _add_card_to_user_direct,
                owner_id, category, name
            )

            if success:
                stats["exchange_board"]["restored"] += 1
                exchange_users.add(owner_id)
                logger.info(f"Restauree: {category}/{name} -> User {owner_id}")

                # Supprimer l'entree du tableau
                await asyncio.to_thread(
                    card_system.storage.delete_exchange_entry,
                    entry_id
                )
            else:
                stats["exchange_board"]["errors"] += 1
                logger.error(f"Echec restauration: {category}/{name} -> User {owner_id}")

        stats["exchange_board"]["users"] = list(exchange_users)

        # Phase 2: Migrer le vault
        logger.info("=== MIGRATION: Phase 2 - Vault ===")

        vault_data = await asyncio.to_thread(
            lambda: card_system.storage.sheet_vault.get_all_values()
        )

        vault_users = set()
        cards_to_restore = []

        # Collecter toutes les cartes a restaurer
        for row in vault_data[1:]:  # Skip header
            if len(row) < 3:
                continue

            category = row[0]
            name = row[1]

            for cell in row[2:]:
                if not cell:
                    continue
                try:
                    uid, count = cell.split(":", 1)
                    uid = int(uid.strip())
                    count = int(count)

                    for _ in range(count):
                        cards_to_restore.append((uid, category, name))

                except (ValueError, IndexError) as e:
                    logger.warning(f"Cellule invalide ignoree: {cell} - {e}")
                    stats["vault"]["errors"] += 1

        # Restaurer les cartes
        for uid, category, name in cards_to_restore:
            success = await asyncio.to_thread(
                _add_card_to_user_direct,
                uid, category, name
            )

            if success:
                stats["vault"]["restored"] += 1
                vault_users.add(uid)
                logger.info(f"Restauree du vault: {category}/{name} -> User {uid}")
            else:
                stats["vault"]["errors"] += 1
                logger.error(f"Echec restauration vault: {category}/{name} -> User {uid}")

        stats["vault"]["users"] = list(vault_users)

        # Vider le vault
        if stats["vault"]["restored"] > 0:
            # Supprimer toutes les lignes sauf l'en-tete
            vault_sheet = card_system.storage.sheet_vault
            all_values = await asyncio.to_thread(vault_sheet.get_all_values)
            if len(all_values) > 1:
                await asyncio.to_thread(
                    vault_sheet.delete_rows,
                    2, len(all_values)
                )
                logger.info("Vault vide")

        # Phase 3: Vider la feuille des echanges hebdomadaires
        logger.info("=== MIGRATION: Phase 3 - Nettoyage ===")

        try:
            weekly_sheet = card_system.storage.sheet_weekly_exchanges
            weekly_data = await asyncio.to_thread(weekly_sheet.get_all_values)
            if len(weekly_data) > 1:
                await asyncio.to_thread(
                    weekly_sheet.delete_rows,
                    2, len(weekly_data)
                )
                logger.info("Feuille 'Echanges Hebdomadaires' videe")
        except Exception as e:
            logger.warning(f"Erreur lors du nettoyage des echanges hebdomadaires: {e}")

        stats["success"] = True

        logger.info("=== MIGRATION TERMINEE ===")
        logger.info(f"Tableau d'echange: {stats['exchange_board']['restored']} cartes restaurees")
        logger.info(f"Vault: {stats['vault']['restored']} cartes restaurees")

        return stats

    except Exception as e:
        logger.error(f"Erreur lors de la migration: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur: {str(e)}"
        )
