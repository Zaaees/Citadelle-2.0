"""
Gestionnaire de logging pour le système de cartes.
Surveille et enregistre toutes les opérations sur les cartes.
"""

import logging
from datetime import datetime
import pytz
from typing import Optional, Dict, Any, TYPE_CHECKING
import json

if TYPE_CHECKING:
    from .storage import CardsStorage


class CardsLoggingManager:
    """Gestionnaire de logging pour toutes les opérations sur les cartes."""
    
    # Types d'actions surveillées
    ACTION_DRAW_NORMAL = "DRAW_NORMAL"
    ACTION_DRAW_DAILY = "DRAW_DAILY"
    ACTION_DRAW_SACRIFICIAL = "DRAW_SACRIFICIAL"
    ACTION_DRAW_BONUS = "DRAW_BONUS"
    ACTION_TRADE_DIRECT = "TRADE_DIRECT"
    ACTION_TRADE_VAULT = "TRADE_VAULT"
    ACTION_EXCHANGE_WEEKLY = "EXCHANGE_WEEKLY"
    ACTION_VAULT_DEPOSIT = "VAULT_DEPOSIT"
    ACTION_VAULT_WITHDRAW = "VAULT_WITHDRAW"
    ACTION_VAULT_CLEAR = "VAULT_CLEAR"
    ACTION_BONUS_GRANTED = "BONUS_GRANTED"
    ACTION_BONUS_USED = "BONUS_USED"
    ACTION_CARD_SACRIFICE = "CARD_SACRIFICE"
    ACTION_ADMIN_ADD = "ADMIN_ADD"
    ACTION_ADMIN_REMOVE = "ADMIN_REMOVE"
    ACTION_CARD_UPGRADE = "CARD_UPGRADE"
    
    def __init__(self, storage: "CardsStorage"):
        self.storage = storage
        self.paris_tz = pytz.timezone("Europe/Paris")
    
    def _get_timestamp(self) -> str:
        """Génère un timestamp au format ISO avec timezone Paris."""
        return datetime.now(self.paris_tz).isoformat()
    
    def _log_action(self, action: str, user_id: int, user_name: str = None,
                   card_category: str = None, card_name: str = None,
                   quantity: int = None, details: str = None,
                   source: str = None, additional_data: Dict[str, Any] = None) -> bool:
        """
        Enregistre une action dans la feuille de logs.

        Args:
            action: Type d'action (constante ACTION_*)
            user_id: ID de l'utilisateur
            user_name: Nom de l'utilisateur (optionnel)
            card_category: Catégorie de la carte (optionnel)
            card_name: Nom de la carte (optionnel)
            quantity: Quantité concernée (optionnel)
            details: Détails supplémentaires (optionnel)
            source: Source de l'action (optionnel)
            additional_data: Données supplémentaires au format dict (optionnel)

        Returns:
            bool: True si l'enregistrement a réussi
        """
        try:
            # Vérifier que la feuille de logs existe
            if not hasattr(self.storage, 'sheet_logs') or self.storage.sheet_logs is None:
                logging.error(f"[LOGS] Feuille de logs non disponible")
                return False

            timestamp = self._get_timestamp()

            # Préparer les données
            row_data = [
                timestamp,
                action,
                str(user_id),
                user_name or f"User_{user_id}",
                card_category or "",
                card_name or "",
                str(quantity) if quantity is not None else "",
                details or "",
                source or "",
                json.dumps(additional_data) if additional_data else ""
            ]

            logging.debug(f"[LOGS] Tentative d'enregistrement: {action} pour user {user_id}")
            logging.debug(f"[LOGS] Données à enregistrer: {row_data}")

            # Enregistrer dans la feuille
            self.storage.sheet_logs.append_row(row_data)

            logging.info(f"[LOGS] ✅ Action enregistrée avec succès: {action} pour user {user_id}")
            return True

        except Exception as e:
            logging.error(f"[LOGS] ❌ Erreur lors de l'enregistrement: {e}")
            logging.error(f"[LOGS] Action: {action}, User: {user_id}, Card: {card_name}")
            import traceback
            logging.error(f"[LOGS] Traceback: {traceback.format_exc()}")
            return False
    
    def log_card_draw(self, user_id: int, user_name: str, cards: list, 
                     draw_type: str, source: str = None) -> bool:
        """
        Enregistre un tirage de cartes.
        
        Args:
            user_id: ID de l'utilisateur
            user_name: Nom de l'utilisateur
            cards: Liste des cartes tirées [(category, name), ...]
            draw_type: Type de tirage (NORMAL, DAILY, SACRIFICIAL, BONUS)
            source: Source du tirage (optionnel)
        """
        action_map = {
            "NORMAL": self.ACTION_DRAW_NORMAL,
            "DAILY": self.ACTION_DRAW_DAILY,
            "SACRIFICIAL": self.ACTION_DRAW_SACRIFICIAL,
            "BONUS": self.ACTION_DRAW_BONUS
        }
        
        action = action_map.get(draw_type, self.ACTION_DRAW_NORMAL)
        
        # Enregistrer chaque carte tirée
        success = True
        for category, name in cards:
            if not self._log_action(
                action=action,
                user_id=user_id,
                user_name=user_name,
                card_category=category,
                card_name=name,
                quantity=1,
                details=f"Tirage {draw_type.lower()}",
                source=source,
                additional_data={"total_cards_drawn": len(cards)}
            ):
                success = False
        
        return success
    
    def log_card_add(self, user_id: int, user_name: str, category: str, name: str,
                    quantity: int = 1, source: str = None, details: str = None) -> bool:
        """Enregistre l'ajout d'une carte à l'inventaire."""
        return self._log_action(
            action=self.ACTION_ADMIN_ADD,
            user_id=user_id,
            user_name=user_name,
            card_category=category,
            card_name=name,
            quantity=quantity,
            details=details or "Ajout de carte",
            source=source
        )
    
    def log_card_remove(self, user_id: int, user_name: str, category: str, name: str,
                       quantity: int = 1, source: str = None, details: str = None) -> bool:
        """Enregistre le retrait d'une carte de l'inventaire."""
        return self._log_action(
            action=self.ACTION_ADMIN_REMOVE,
            user_id=user_id,
            user_name=user_name,
            card_category=category,
            card_name=name,
            quantity=quantity,
            details=details or "Retrait de carte",
            source=source
        )
    
    def log_trade_direct(self, offerer_id: int, offerer_name: str, target_id: int, target_name: str,
                        offer_card: tuple, return_card: tuple, source: str = None) -> bool:
        """Enregistre un échange direct entre deux utilisateurs."""
        offer_cat, offer_name = offer_card
        return_cat, return_name = return_card
        
        # Enregistrer pour le proposeur (perte)
        success1 = self._log_action(
            action=self.ACTION_TRADE_DIRECT,
            user_id=offerer_id,
            user_name=offerer_name,
            card_category=offer_cat,
            card_name=offer_name,
            quantity=-1,
            details=f"Échange avec {target_name} - Carte donnée",
            source=source,
            additional_data={
                "trade_partner_id": target_id,
                "trade_partner_name": target_name,
                "received_card": f"{return_cat}:{return_name}"
            }
        )
        
        # Enregistrer pour le proposeur (gain)
        success2 = self._log_action(
            action=self.ACTION_TRADE_DIRECT,
            user_id=offerer_id,
            user_name=offerer_name,
            card_category=return_cat,
            card_name=return_name,
            quantity=1,
            details=f"Échange avec {target_name} - Carte reçue",
            source=source,
            additional_data={
                "trade_partner_id": target_id,
                "trade_partner_name": target_name,
                "given_card": f"{offer_cat}:{offer_name}"
            }
        )
        
        # Enregistrer pour la cible (perte)
        success3 = self._log_action(
            action=self.ACTION_TRADE_DIRECT,
            user_id=target_id,
            user_name=target_name,
            card_category=return_cat,
            card_name=return_name,
            quantity=-1,
            details=f"Échange avec {offerer_name} - Carte donnée",
            source=source,
            additional_data={
                "trade_partner_id": offerer_id,
                "trade_partner_name": offerer_name,
                "received_card": f"{offer_cat}:{offer_name}"
            }
        )
        
        # Enregistrer pour la cible (gain)
        success4 = self._log_action(
            action=self.ACTION_TRADE_DIRECT,
            user_id=target_id,
            user_name=target_name,
            card_category=offer_cat,
            card_name=offer_name,
            quantity=1,
            details=f"Échange avec {offerer_name} - Carte reçue",
            source=source,
            additional_data={
                "trade_partner_id": offerer_id,
                "trade_partner_name": offerer_name,
                "given_card": f"{return_cat}:{return_name}"
            }
        )
        
        return success1 and success2 and success3 and success4

    def log_trade_vault(self, user1_id: int, user1_name: str, user2_id: int, user2_name: str,
                       user1_cards: list, user2_cards: list, source: str = None) -> bool:
        """Enregistre un échange de vault complet."""
        success = True

        # Enregistrer les cartes perdues par user1
        for category, name in user1_cards:
            if not self._log_action(
                action=self.ACTION_TRADE_VAULT,
                user_id=user1_id,
                user_name=user1_name,
                card_category=category,
                card_name=name,
                quantity=-1,
                details=f"Échange de vault avec {user2_name} - Carte donnée",
                source=source,
                additional_data={
                    "trade_partner_id": user2_id,
                    "trade_partner_name": user2_name,
                    "vault_exchange": True
                }
            ):
                success = False

        # Enregistrer les cartes gagnées par user1
        for category, name in user2_cards:
            if not self._log_action(
                action=self.ACTION_TRADE_VAULT,
                user_id=user1_id,
                user_name=user1_name,
                card_category=category,
                card_name=name,
                quantity=1,
                details=f"Échange de vault avec {user2_name} - Carte reçue",
                source=source,
                additional_data={
                    "trade_partner_id": user2_id,
                    "trade_partner_name": user2_name,
                    "vault_exchange": True
                }
            ):
                success = False

        # Enregistrer les cartes perdues par user2
        for category, name in user2_cards:
            if not self._log_action(
                action=self.ACTION_TRADE_VAULT,
                user_id=user2_id,
                user_name=user2_name,
                card_category=category,
                card_name=name,
                quantity=-1,
                details=f"Échange de vault avec {user1_name} - Carte donnée",
                source=source,
                additional_data={
                    "trade_partner_id": user1_id,
                    "trade_partner_name": user1_name,
                    "vault_exchange": True
                }
            ):
                success = False

        # Enregistrer les cartes gagnées par user2
        for category, name in user1_cards:
            if not self._log_action(
                action=self.ACTION_TRADE_VAULT,
                user_id=user2_id,
                user_name=user2_name,
                card_category=category,
                card_name=name,
                quantity=1,
                details=f"Échange de vault avec {user1_name} - Carte reçue",
                source=source,
                additional_data={
                    "trade_partner_id": user1_id,
                    "trade_partner_name": user1_name,
                    "vault_exchange": True
                }
            ):
                success = False

        return success

    def log_vault_operation(self, user_id: int, user_name: str, category: str, name: str,
                           operation: str, quantity: int = 1, source: str = None) -> bool:
        """Enregistre une opération sur le vault (dépôt/retrait)."""
        action = self.ACTION_VAULT_DEPOSIT if operation == "DEPOSIT" else self.ACTION_VAULT_WITHDRAW
        details = f"Dépôt au vault" if operation == "DEPOSIT" else f"Retrait du vault"

        return self._log_action(
            action=action,
            user_id=user_id,
            user_name=user_name,
            card_category=category,
            card_name=name,
            quantity=quantity if operation == "DEPOSIT" else -quantity,
            details=details,
            source=source
        )

    def log_vault_clear(self, user_id: int, user_name: str, cards: list, source: str = None) -> bool:
        """Enregistre le vidage complet d'un vault."""
        success = True

        for category, name in cards:
            if not self._log_action(
                action=self.ACTION_VAULT_CLEAR,
                user_id=user_id,
                user_name=user_name,
                card_category=category,
                card_name=name,
                quantity=-1,
                details="Vidage complet du vault",
                source=source
            ):
                success = False

        return success

    def log_weekly_exchange(self, user_id: int, user_name: str, given_cards: list,
                           received_cards: list, source: str = None) -> bool:
        """Enregistre un échange hebdomadaire."""
        success = True

        # Enregistrer les cartes données
        for category, name in given_cards:
            if not self._log_action(
                action=self.ACTION_EXCHANGE_WEEKLY,
                user_id=user_id,
                user_name=user_name,
                card_category=category,
                card_name=name,
                quantity=-1,
                details="Échange hebdomadaire - Carte donnée",
                source=source,
                additional_data={"weekly_exchange": True}
            ):
                success = False

        # Enregistrer les cartes reçues
        for category, name in received_cards:
            if not self._log_action(
                action=self.ACTION_EXCHANGE_WEEKLY,
                user_id=user_id,
                user_name=user_name,
                card_category=category,
                card_name=name,
                quantity=1,
                details="Échange hebdomadaire - Carte reçue",
                source=source,
                additional_data={"weekly_exchange": True}
            ):
                success = False

        return success

    def log_card_sacrifice(self, user_id: int, user_name: str, sacrificed_cards: list,
                          received_cards: list, source: str = None) -> bool:
        """Enregistre un sacrifice de cartes."""
        success = True

        # Enregistrer les cartes sacrifiées
        for category, name in sacrificed_cards:
            if not self._log_action(
                action=self.ACTION_CARD_SACRIFICE,
                user_id=user_id,
                user_name=user_name,
                card_category=category,
                card_name=name,
                quantity=-1,
                details="Sacrifice de carte",
                source=source,
                additional_data={"sacrificial_draw": True}
            ):
                success = False

        # Enregistrer les cartes reçues
        for category, name in received_cards:
            if not self._log_action(
                action=self.ACTION_DRAW_SACRIFICIAL,
                user_id=user_id,
                user_name=user_name,
                card_category=category,
                card_name=name,
                quantity=1,
                details="Tirage sacrificiel - Carte reçue",
                source=source,
                additional_data={"sacrificial_draw": True}
            ):
                success = False

        return success

    def log_bonus_granted(self, user_id: int, user_name: str, count: int,
                         source: str, granted_by: str = None) -> bool:
        """Enregistre l'attribution d'un bonus."""
        return self._log_action(
            action=self.ACTION_BONUS_GRANTED,
            user_id=user_id,
            user_name=user_name,
            quantity=count,
            details=f"Bonus accordé: {count} tirage(s)",
            source=source,
            additional_data={"granted_by": granted_by} if granted_by else None
        )

    def log_bonus_used(self, user_id: int, user_name: str, count: int,
                      cards: list, source: str = None) -> bool:
        """Enregistre l'utilisation d'un bonus."""
        success = True

        # Enregistrer l'utilisation du bonus
        if not self._log_action(
            action=self.ACTION_BONUS_USED,
            user_id=user_id,
            user_name=user_name,
            quantity=count,
            details=f"Utilisation de {count} bonus",
            source=source,
            additional_data={"cards_drawn": len(cards)}
        ):
            success = False

        # Enregistrer les cartes tirées avec le bonus
        for category, name in cards:
            if not self._log_action(
                action=self.ACTION_DRAW_BONUS,
                user_id=user_id,
                user_name=user_name,
                card_category=category,
                card_name=name,
                quantity=1,
                details="Tirage bonus",
                source=source
            ):
                success = False

        return success

    def log_card_upgrade(self, user_id: int, user_name: str, base_cards: list,
                        upgraded_card: tuple, source: str = None) -> bool:
        """Enregistre un upgrade de carte (5 cartes normales -> 1 carte Full)."""
        success = True

        # Enregistrer les cartes de base utilisées
        for category, name in base_cards:
            if not self._log_action(
                action=self.ACTION_CARD_UPGRADE,
                user_id=user_id,
                user_name=user_name,
                card_category=category,
                card_name=name,
                quantity=-1,
                details="Upgrade de carte - Carte utilisée",
                source=source,
                additional_data={"upgrade": True}
            ):
                success = False

        # Enregistrer la carte Full obtenue
        category, name = upgraded_card
        if not self._log_action(
            action=self.ACTION_CARD_UPGRADE,
            user_id=user_id,
            user_name=user_name,
            card_category=category,
            card_name=name,
            quantity=1,
            details="Upgrade de carte - Carte Full obtenue",
            source=source,
            additional_data={"upgrade": True, "full_card": True}
        ):
            success = False

        return success
