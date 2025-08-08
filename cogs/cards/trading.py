"""
Logique de trading et d'échange des cartes.
"""

import logging
from typing import List, Tuple, Optional
from datetime import datetime, timedelta
import pytz

from .storage import CardsStorage
from .vault import VaultManager
from .utils import validate_card_data
from .config import WEEKLY_EXCHANGE_LIMIT


class TradingManager:
    """Gestionnaire des échanges de cartes."""
    
    def __init__(self, storage: CardsStorage, vault_manager: VaultManager):
        self.storage = storage
        self.vault_manager = vault_manager

    # ------------------------------------------------------------------
    # Tableau d'échanges
    # ------------------------------------------------------------------

    def list_board_offers(self) -> List[dict]:
        """Retourne toutes les offres présentes sur le tableau d'échanges."""
        return self.storage.get_exchange_entries()

    def deposit_to_board(self, user_id: int, cat: str, name: str) -> bool:
        """Dépose une carte sur le tableau d'échanges."""
        try:
            if not validate_card_data(cat, name, user_id):
                return False

            if not self._user_has_card(user_id, cat, name):
                logging.error(f"[BOARD] Utilisateur {user_id} ne possède pas la carte ({cat}, {name})")
                return False

            timestamp = datetime.now(pytz.timezone("Europe/Paris")).isoformat()

            with self.storage._cards_lock, self.storage._board_lock:
                if not self._remove_card_from_user(user_id, cat, name):
                    return False
                entry_id = self.storage.create_exchange_entry(user_id, cat, name, timestamp)
                if entry_id is None:
                    self._add_card_to_user(user_id, cat, name)
                    return False

            if self.storage.logging_manager:
                self.storage.logging_manager.log_card_remove(
                    user_id=user_id,
                    user_name=f"User_{user_id}",
                    category=cat,
                    name=name,
                    details="Déposé sur le tableau d'échanges",
                    source="board_deposit"
                )

            return True

        except Exception as e:
            logging.error(f"[BOARD] Erreur lors du dépôt: {e}")
            return False

    def initiate_board_trade(self, user_id: int, board_id: int,
                             offered_cat: str, offered_name: str) -> Optional[Tuple[int, str, str]]:
        """Vérifie une proposition d'échange sans la réaliser.

        Retourne les informations de l'offre si la proposition est valide,
        sinon ``None``.
        """
        try:
            if not validate_card_data(offered_cat, offered_name, user_id):
                return None

            with self.storage._cards_lock, self.storage._board_lock:
                entry = self.storage.get_exchange_entry(board_id)
                if not entry:
                    return None

                owner_id = int(entry["owner"])
                board_cat = entry["cat"]
                board_name = entry["name"]

            if offered_cat != board_cat:
                logging.error(f"[BOARD] Catégorie proposée {offered_cat} différente de {board_cat}")
                return None

            if not self._user_has_card(user_id, offered_cat, offered_name):
                logging.error(f"[BOARD] Utilisateur {user_id} ne possède pas la carte proposée")
                return None

            return owner_id, board_cat, board_name

        except Exception as e:
            logging.error(f"[BOARD] Erreur lors de la validation de l'échange: {e}")
            return None

    def take_from_board(self, user_id: int, board_id: int,
                        offered_cat: str, offered_name: str) -> bool:
        """Finalise un échange après confirmation du propriétaire."""
        try:
            if not validate_card_data(offered_cat, offered_name, user_id):
                return False

            with self.storage._cards_lock, self.storage._board_lock:
                entry = self.storage.get_exchange_entry(board_id)
                if not entry:
                    return False

                owner_id = int(entry["owner"])
                board_cat = entry["cat"]
                board_name = entry["name"]

                # Valider la carte proposée
                if offered_cat != board_cat:
                    logging.error(f"[BOARD] Catégorie proposée {offered_cat} différente de {board_cat}")
                    return False

                if not self._user_has_card(user_id, offered_cat, offered_name):
                    logging.error(f"[BOARD] Utilisateur {user_id} ne possède pas la carte proposée")
                    return False

                # Retirer la carte offerte du preneur
                if not self._remove_card_from_user(user_id, offered_cat, offered_name):
                    return False

                # Ajouter la carte offerte au propriétaire
                if not self._add_card_to_user(owner_id, offered_cat, offered_name):
                    self._add_card_to_user(user_id, offered_cat, offered_name)
                    return False

                # Donner la carte du tableau au preneur
                if not self._add_card_to_user(user_id, board_cat, board_name):
                    self._remove_card_from_user(owner_id, offered_cat, offered_name)
                    self._add_card_to_user(user_id, offered_cat, offered_name)
                    return False

                # Supprimer l'entrée du tableau
                if not self.storage.delete_exchange_entry(board_id):
                    # Rollback complet
                    self._remove_card_from_user(user_id, board_cat, board_name)
                    self._remove_card_from_user(owner_id, offered_cat, offered_name)
                    self._add_card_to_user(user_id, offered_cat, offered_name)
                    return False

            if self.storage.logging_manager:
                self.storage.logging_manager.log_trade_direct(
                    offerer_id=user_id,
                    offerer_name=f"User_{user_id}",
                    target_id=owner_id,
                    target_name=f"User_{owner_id}",
                    offer_card=(offered_cat, offered_name),
                    return_card=(board_cat, board_name),
                    source="board_exchange"
                )

            if hasattr(self.storage, '_cog_ref'):
                self.storage._cog_ref._mark_user_for_upgrade_check(user_id)
                self.storage._cog_ref._mark_user_for_upgrade_check(owner_id)

            return True

        except Exception as e:
            logging.error(f"[BOARD] Erreur lors de l'échange: {e}")
            return False

    def withdraw_from_board(self, user_id: int, board_id: int) -> bool:
        """Retire une offre du tableau et rend la carte au propriétaire."""
        try:
            with self.storage._cards_lock, self.storage._board_lock:
                entry = self.storage.get_exchange_entry(board_id)
                if not entry or int(entry["owner"]) != user_id:
                    return False

                cat = entry["cat"]
                name = entry["name"]
                timestamp = entry["timestamp"]

                if not self.storage.delete_exchange_entry(board_id):
                    return False

                if not self._add_card_to_user(user_id, cat, name):
                    # Rollback si impossible de rendre la carte
                    self.storage.create_exchange_entry(user_id, cat, name, timestamp)
                    return False

            if self.storage.logging_manager:
                self.storage.logging_manager.log_card_add(
                    user_id=user_id,
                    user_name=f"User_{user_id}",
                    category=cat,
                    name=name,
                    details="Retrait du tableau d'échanges",
                    source="board_withdraw",
                )

            return True

        except Exception as e:
            logging.error(f"[BOARD] Erreur lors du retrait: {e}")
            return False

    def cleanup_board(self, max_age_hours: int = 24) -> None:
        """Retire les offres expirées et restitue les cartes."""
        try:
            now = datetime.now(pytz.timezone("Europe/Paris"))
            entries = self.list_board_offers()
            for entry in entries:
                try:
                    ts = datetime.fromisoformat(entry["timestamp"])
                except Exception:
                    ts = None

                if ts and now - ts < timedelta(hours=max_age_hours):
                    continue

                owner_id = int(entry["owner"])
                cat = entry["cat"]
                name = entry["name"]
                entry_id = int(entry["id"])

                with self.storage._cards_lock, self.storage._board_lock:
                    if self.storage.delete_exchange_entry(entry_id):
                        self._add_card_to_user(owner_id, cat, name)
                        if self.storage.logging_manager:
                            self.storage.logging_manager.log_card_add(
                                user_id=owner_id,
                                user_name=f"User_{owner_id}",
                                category=cat,
                                name=name,
                                details="Retour après expiration du tableau",
                                source="board_cleanup"
                            )
        except Exception as e:
            logging.error(f"[BOARD] Erreur lors du nettoyage du tableau: {e}")
    
    def safe_exchange(self, offerer_id: int, target_id: int, 
                     offer_cat: str, offer_name: str, 
                     return_cat: str, return_name: str) -> bool:
        """
        Effectue un échange sécurisé entre deux utilisateurs.
        
        Args:
            offerer_id: ID de l'utilisateur qui propose
            target_id: ID de l'utilisateur cible
            offer_cat: Catégorie de la carte proposée
            offer_name: Nom de la carte proposée
            return_cat: Catégorie de la carte demandée
            return_name: Nom de la carte demandée
        
        Returns:
            bool: True si l'échange a réussi
        """
        try:
            # Validation des paramètres
            if not all([validate_card_data(offer_cat, offer_name, offerer_id),
                       validate_card_data(return_cat, return_name, target_id)]):
                return False
            
            # Vérifier que les deux utilisateurs possèdent leurs cartes respectives
            if not self._user_has_card(offerer_id, offer_cat, offer_name):
                logging.error(f"[TRADING] L'utilisateur {offerer_id} ne possède pas la carte ({offer_cat}, {offer_name})")
                return False
            
            if not self._user_has_card(target_id, return_cat, return_name):
                logging.error(f"[TRADING] L'utilisateur {target_id} ne possède pas la carte ({return_cat}, {return_name})")
                return False
            
            # Effectuer l'échange atomique
            with self.storage._cards_lock:
                # Retirer les cartes des inventaires respectifs
                if not self._remove_card_from_user(offerer_id, offer_cat, offer_name):
                    return False
                
                if not self._remove_card_from_user(target_id, return_cat, return_name):
                    # Rollback: remettre la carte du proposeur
                    self._add_card_to_user(offerer_id, offer_cat, offer_name)
                    return False
                
                # Ajouter les cartes aux nouveaux propriétaires
                if not self._add_card_to_user(target_id, offer_cat, offer_name):
                    # Rollback complet
                    self._add_card_to_user(offerer_id, offer_cat, offer_name)
                    self._add_card_to_user(target_id, return_cat, return_name)
                    return False
                
                if not self._add_card_to_user(offerer_id, return_cat, return_name):
                    # Rollback complet
                    self._remove_card_from_user(target_id, offer_cat, offer_name)
                    self._add_card_to_user(offerer_id, offer_cat, offer_name)
                    self._add_card_to_user(target_id, return_cat, return_name)
                    return False
            
            logging.info(f"[TRADING] Échange réussi: {offerer_id} <-> {target_id}, cartes: ({offer_cat}, {offer_name}) <-> ({return_cat}, {return_name})")

            # Logger l'échange direct
            if self.storage.logging_manager:
                # Récupérer les noms des utilisateurs (approximatif)
                offerer_name = f"User_{offerer_id}"
                target_name = f"User_{target_id}"

                self.storage.logging_manager.log_trade_direct(
                    offerer_id=offerer_id,
                    offerer_name=offerer_name,
                    target_id=target_id,
                    target_name=target_name,
                    offer_card=(offer_cat, offer_name),
                    return_card=(return_cat, return_name),
                    source="echange_direct"
                )

            # Marquer que les vérifications d'upgrade sont nécessaires via le cog principal
            if hasattr(self.storage, '_cog_ref'):
                self.storage._cog_ref._mark_user_for_upgrade_check(offerer_id)
                self.storage._cog_ref._mark_user_for_upgrade_check(target_id)

            return True
            
        except Exception as e:
            logging.error(f"[TRADING] Erreur lors de l'échange: {e}")
            return False
    
    def execute_full_vault_trade(self, user1_id: int, user2_id: int) -> bool:
        """
        Effectue un échange complet des vaults entre deux utilisateurs.
        
        Args:
            user1_id: ID du premier utilisateur
            user2_id: ID du second utilisateur
        
        Returns:
            bool: True si l'échange a réussi
        """
        try:
            # Récupérer les cartes des deux vaults
            user1_vault = self.vault_manager.get_user_vault_cards(user1_id)
            user2_vault = self.vault_manager.get_user_vault_cards(user2_id)
            
            # Vider les deux vaults
            if not self.vault_manager.clear_user_vault(user1_id):
                return False
            
            if not self.vault_manager.clear_user_vault(user2_id):
                # Rollback: remettre les cartes du premier utilisateur
                for cat, name in user1_vault:
                    self.vault_manager.add_card_to_vault(user1_id, cat, name, skip_possession_check=True)
                return False
            
            # Échanger les contenus
            success = True
            
            # Ajouter les cartes de user1 à user2
            for cat, name in user1_vault:
                if not self.vault_manager.add_card_to_vault(user2_id, cat, name, skip_possession_check=True):
                    success = False
                    break
            
            # Ajouter les cartes de user2 à user1
            if success:
                for cat, name in user2_vault:
                    if not self.vault_manager.add_card_to_vault(user1_id, cat, name, skip_possession_check=True):
                        success = False
                        break
            
            if not success:
                # Rollback complet
                self.vault_manager.clear_user_vault(user1_id)
                self.vault_manager.clear_user_vault(user2_id)
                for cat, name in user1_vault:
                    self.vault_manager.add_card_to_vault(user1_id, cat, name, skip_possession_check=True)
                for cat, name in user2_vault:
                    self.vault_manager.add_card_to_vault(user2_id, cat, name, skip_possession_check=True)
                return False
            
            logging.info(f"[TRADING] Échange de vault complet réussi entre {user1_id} et {user2_id}")

            # Logger l'échange de vault
            if self.storage.logging_manager:
                user1_name = f"User_{user1_id}"
                user2_name = f"User_{user2_id}"

                self.storage.logging_manager.log_trade_vault(
                    user1_id=user1_id,
                    user1_name=user1_name,
                    user2_id=user2_id,
                    user2_name=user2_name,
                    user1_cards=user1_vault,
                    user2_cards=user2_vault,
                    source="echange_vault"
                )

            # Marquer que les vérifications d'upgrade sont nécessaires via le cog principal
            if hasattr(self.storage, '_cog_ref'):
                self.storage._cog_ref._mark_user_for_upgrade_check(user1_id)
                self.storage._cog_ref._mark_user_for_upgrade_check(user2_id)

            return True
            
        except Exception as e:
            logging.error(f"[TRADING] Erreur lors de l'échange de vault: {e}")
            return False


    
    def can_perform_weekly_exchange(self, user_id: int) -> bool:
        """
        Vérifie si un utilisateur peut effectuer un échange hebdomadaire.
        
        Args:
            user_id: ID de l'utilisateur
        
        Returns:
            bool: True si l'échange est autorisé
        """
        try:
            # Calculer la semaine actuelle (lundi = début de semaine, timezone Paris)
            paris_tz = pytz.timezone("Europe/Paris")
            now = datetime.now(paris_tz)
            monday = now - timedelta(days=now.weekday())
            week_key = monday.strftime("%Y-W%U")
            
            # Vérifier dans la feuille des échanges hebdomadaires
            all_rows = self.storage.sheet_weekly_exchanges.get_all_values()
            user_id_str = str(user_id)
            
            for row in all_rows:
                if len(row) >= 3 and row[0] == user_id_str and row[1] == week_key:
                    current_count = int(row[2])
                    return current_count < WEEKLY_EXCHANGE_LIMIT
            
            return True  # Aucun échange cette semaine
            
        except Exception as e:
            logging.error(f"[TRADING] Erreur lors de la vérification des échanges hebdomadaires: {e}")
            return False
    
    def record_weekly_exchange(self, user_id: int) -> bool:
        """
        Enregistre qu'un utilisateur a effectué un échange hebdomadaire.
        
        Args:
            user_id: ID de l'utilisateur
        
        Returns:
            bool: True si l'enregistrement a réussi
        """
        try:
            # Calculer la semaine actuelle
            paris_tz = pytz.timezone("Europe/Paris")
            now = datetime.now(paris_tz)
            monday = now - timedelta(days=now.weekday())
            week_key = monday.strftime("%Y-W%U")
            user_id_str = str(user_id)
            
            # Mettre à jour ou ajouter l'entrée
            all_rows = self.storage.sheet_weekly_exchanges.get_all_values()
            row_idx = None
            current_count = 0
            
            for i, row in enumerate(all_rows):
                if len(row) >= 3 and row[0] == user_id_str and row[1] == week_key:
                    row_idx = i
                    current_count = int(row[2])
                    break
            
            if row_idx is not None:
                # Mettre à jour la ligne existante
                self.storage.sheet_weekly_exchanges.update(f"C{row_idx + 1}", str(current_count + 1))
            else:
                # Ajouter une nouvelle ligne
                self.storage.sheet_weekly_exchanges.append_row([user_id_str, week_key, "1"])
            
            # Marquer que cet utilisateur a besoin d'une vérification d'upgrade via le cog principal
            if hasattr(self.storage, '_cog_ref'):
                self.storage._cog_ref._mark_user_for_upgrade_check(user_id)

            logging.info(f"[TRADING] Échange hebdomadaire enregistré pour l'utilisateur {user_id}")
            return True
            
        except Exception as e:
            logging.error(f"[TRADING] Erreur lors de l'enregistrement de l'échange hebdomadaire: {e}")
            return False
    
    def _user_has_card(self, user_id: int, category: str, name: str) -> bool:
        """Vérifie si un utilisateur possède une carte spécifique."""
        # Cette méthode sera implémentée avec la logique de vérification des cartes
        # Pour l'instant, retourne True (sera complétée lors de l'intégration)
        return True
    
    def _add_card_to_user(self, user_id: int, category: str, name: str) -> bool:
        """Ajoute une carte à l'inventaire d'un utilisateur."""
        # Cette méthode sera implémentée avec la logique d'ajout de cartes
        # Pour l'instant, retourne True (sera complétée lors de l'intégration)
        return True
    
    def _remove_card_from_user(self, user_id: int, category: str, name: str) -> bool:
        """Retire une carte de l'inventaire d'un utilisateur."""
        # Cette méthode sera implémentée avec la logique de retrait de cartes
        # Pour l'instant, retourne True (sera complétée lors de l'intégration)
        return True
