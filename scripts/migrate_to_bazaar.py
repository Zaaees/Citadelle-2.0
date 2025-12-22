"""
Script de migration vers le systeme Bazaar.

Ce script :
1. Restaure toutes les cartes du tableau d'echange aux proprietaires
2. Restaure toutes les cartes des coffres (vault) aux proprietaires
3. Vide les sheets "Tableau Echanges" et "Vault"
4. Supprime la sheet "Echanges Hebdomadaires" (plus de limite)

IMPORTANT: Executer ce script UNE SEULE FOIS avant de deployer le nouveau systeme.
"""

import os
import sys
import json
import logging
from datetime import datetime

# Ajouter le repertoire parent au path pour importer les modules du bot
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gspread
from google.oauth2.service_account import Credentials

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Scopes Google
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]


def get_gspread_client():
    """Initialise le client gspread."""
    service_account_json = os.getenv('SERVICE_ACCOUNT_JSON')
    if not service_account_json:
        raise ValueError("SERVICE_ACCOUNT_JSON non defini")

    creds_dict = json.loads(service_account_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)


def migrate_exchange_board(spreadsheet, cards_sheet) -> dict:
    """
    Restaure les cartes du tableau d'echange aux proprietaires.

    Returns:
        dict: Statistiques de migration
    """
    stats = {"restored": 0, "errors": 0, "users": set()}

    try:
        exchange_sheet = spreadsheet.worksheet("Tableau Echanges")
    except gspread.exceptions.WorksheetNotFound:
        logger.info("Feuille 'Tableau Echanges' non trouvee - rien a migrer")
        return stats

    # Lire toutes les entrees
    records = exchange_sheet.get_all_records()
    logger.info(f"Trouvees {len(records)} cartes sur le tableau d'echange")

    # Lire le cache des cartes
    cards_cache = cards_sheet.get_all_values()

    for entry in records:
        owner_id = entry.get("owner")
        category = entry.get("cat")
        name = entry.get("name")

        if not owner_id or not category or not name:
            logger.warning(f"Entree invalide ignoree: {entry}")
            stats["errors"] += 1
            continue

        owner_id = int(owner_id)

        # Ajouter la carte au proprietaire
        success = add_card_to_inventory(cards_sheet, cards_cache, owner_id, category, name)

        if success:
            stats["restored"] += 1
            stats["users"].add(owner_id)
            logger.info(f"Restauree: {category}/{name} -> User {owner_id}")
        else:
            stats["errors"] += 1
            logger.error(f"Echec restauration: {category}/{name} -> User {owner_id}")

    # Vider le tableau d'echange (garder l'en-tete)
    if len(records) > 0:
        # Supprimer toutes les lignes sauf l'en-tete
        exchange_sheet.delete_rows(2, len(records) + 1)
        logger.info("Tableau d'echange vide")

    stats["users"] = len(stats["users"])
    return stats


def migrate_vault(spreadsheet, cards_sheet) -> dict:
    """
    Restaure les cartes des coffres aux proprietaires.

    Returns:
        dict: Statistiques de migration
    """
    stats = {"restored": 0, "errors": 0, "users": set()}

    try:
        vault_sheet = spreadsheet.worksheet("Vault")
    except gspread.exceptions.WorksheetNotFound:
        logger.info("Feuille 'Vault' non trouvee - rien a migrer")
        return stats

    # Lire toutes les donnees du vault
    vault_data = vault_sheet.get_all_values()
    if len(vault_data) <= 1:  # Seulement l'en-tete
        logger.info("Vault vide - rien a migrer")
        return stats

    # Lire le cache des cartes
    cards_cache = cards_sheet.get_all_values()

    # Parser les donnees du vault (format: category, name, user_id:count, ...)
    for row in vault_data[1:]:  # Skip header
        if len(row) < 3:
            continue

        category = row[0]
        name = row[1]

        # Parser les user_id:count
        for cell in row[2:]:
            if not cell:
                continue

            try:
                uid, count = cell.split(":", 1)
                uid = int(uid.strip())
                count = int(count)

                # Restaurer chaque exemplaire
                for _ in range(count):
                    success = add_card_to_inventory(cards_sheet, cards_cache, uid, category, name)
                    if success:
                        stats["restored"] += 1
                        stats["users"].add(uid)
                        logger.info(f"Restauree du vault: {category}/{name} -> User {uid}")
                    else:
                        stats["errors"] += 1
                        logger.error(f"Echec restauration vault: {category}/{name} -> User {uid}")

            except (ValueError, IndexError) as e:
                logger.warning(f"Cellule invalide ignoree: {cell} - {e}")
                stats["errors"] += 1

    # Vider le vault (garder l'en-tete)
    if len(vault_data) > 1:
        vault_sheet.delete_rows(2, len(vault_data))
        logger.info("Vault vide")

    stats["users"] = len(stats["users"])
    return stats


def add_card_to_inventory(cards_sheet, cards_cache: list, user_id: int, category: str, name: str) -> bool:
    """
    Ajoute une carte a l'inventaire d'un utilisateur.

    Note: Cette fonction modifie cards_cache en place pour les appels suivants.
    """
    try:
        # Chercher la carte dans le cache
        for i, row in enumerate(cards_cache):
            if len(row) >= 2 and row[0] == category and row[1] == name:
                # Carte trouvee, chercher si l'utilisateur existe deja
                for j, cell in enumerate(row[2:], start=2):
                    if not cell:
                        continue
                    try:
                        uid, count = cell.split(":", 1)
                        if int(uid.strip()) == user_id:
                            # Incrementer le count
                            new_count = int(count) + 1
                            row[j] = f"{user_id}:{new_count}"
                            cards_sheet.update_cell(i + 1, j + 1, f"{user_id}:{new_count}")
                            return True
                    except (ValueError, IndexError):
                        continue

                # Utilisateur pas trouve, ajouter une nouvelle cellule
                new_cell = f"{user_id}:1"
                row.append(new_cell)
                # Trouver la premiere colonne vide
                col_index = len([c for c in row if c]) + 1
                cards_sheet.update_cell(i + 1, col_index, new_cell)
                return True

        # Carte non trouvee dans l'inventaire - c'est anormal
        logger.error(f"Carte non trouvee dans l'inventaire: {category}/{name}")
        return False

    except Exception as e:
        logger.error(f"Erreur lors de l'ajout de carte: {e}")
        return False


def cleanup_weekly_exchanges(spreadsheet):
    """Supprime ou vide la feuille des echanges hebdomadaires."""
    try:
        weekly_sheet = spreadsheet.worksheet("Echanges Hebdomadaires")
        # Vider au lieu de supprimer pour eviter les erreurs de reference
        data = weekly_sheet.get_all_values()
        if len(data) > 1:
            weekly_sheet.delete_rows(2, len(data))
        logger.info("Feuille 'Echanges Hebdomadaires' videe")
    except gspread.exceptions.WorksheetNotFound:
        logger.info("Feuille 'Echanges Hebdomadaires' non trouvee")


def main():
    """Fonction principale de migration."""
    logger.info("=" * 60)
    logger.info("MIGRATION VERS LE SYSTEME BAZAAR")
    logger.info("=" * 60)
    logger.info(f"Date: {datetime.now().isoformat()}")

    # Verification de confirmation
    print("\n" + "=" * 60)
    print("ATTENTION: Ce script va:")
    print("1. Restaurer les cartes du tableau d'echange aux proprietaires")
    print("2. Restaurer les cartes des coffres aux proprietaires")
    print("3. Vider le tableau d'echange et les coffres")
    print("4. Vider la feuille des echanges hebdomadaires")
    print("=" * 60)

    confirm = input("\nTaper 'MIGRATE' pour confirmer: ")
    if confirm != "MIGRATE":
        print("Migration annulee.")
        return

    # Initialisation
    logger.info("Connexion a Google Sheets...")
    client = get_gspread_client()

    spreadsheet_id = os.getenv('GOOGLE_SHEET_ID_CARTES')
    if not spreadsheet_id:
        raise ValueError("GOOGLE_SHEET_ID_CARTES non defini")

    spreadsheet = client.open_by_key(spreadsheet_id)
    cards_sheet = spreadsheet.sheet1  # Feuille principale des cartes

    logger.info("Connexion etablie")

    # Phase 1: Migration du tableau d'echange
    logger.info("\n--- PHASE 1: Tableau d'echange ---")
    exchange_stats = migrate_exchange_board(spreadsheet, cards_sheet)
    logger.info(f"Resultats: {exchange_stats['restored']} cartes restaurees, "
                f"{exchange_stats['errors']} erreurs, {exchange_stats['users']} utilisateurs")

    # Phase 2: Migration du vault
    logger.info("\n--- PHASE 2: Coffres (Vault) ---")
    vault_stats = migrate_vault(spreadsheet, cards_sheet)
    logger.info(f"Resultats: {vault_stats['restored']} cartes restaurees, "
                f"{vault_stats['errors']} erreurs, {vault_stats['users']} utilisateurs")

    # Phase 3: Nettoyage
    logger.info("\n--- PHASE 3: Nettoyage ---")
    cleanup_weekly_exchanges(spreadsheet)

    # Resume
    logger.info("\n" + "=" * 60)
    logger.info("MIGRATION TERMINEE")
    logger.info("=" * 60)
    total_restored = exchange_stats["restored"] + vault_stats["restored"]
    total_errors = exchange_stats["errors"] + vault_stats["errors"]
    logger.info(f"Total: {total_restored} cartes restaurees, {total_errors} erreurs")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
