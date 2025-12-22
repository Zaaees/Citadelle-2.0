"""
Service de tirage de cartes
Réplique la logique du bot Discord pour les tirages
"""

import random
from typing import List, Tuple, Optional
from config import RARITY_CONFIG, RARITY_ORDER
from storage import get_storage_service
import logging

logger = logging.getLogger(__name__)


class DrawingService:
    """Service gérant les tirages de cartes"""

    def __init__(self):
        self.storage = get_storage_service()

    def _select_random_category(self) -> str:
        """Sélectionne une catégorie aléatoire selon les poids de rareté"""
        categories = list(RARITY_CONFIG.keys())
        weights = [RARITY_CONFIG[cat]["weight"] for cat in categories]
        return random.choices(categories, weights=weights, k=1)[0]

    def _select_random_card(self, category: str) -> Optional[Tuple[str, str, str]]:
        """
        Sélectionne une carte aléatoire dans une catégorie
        Returns: (category, name, file_id) ou None
        """
        cards = self.storage.cards_by_category.get(category, [])
        if not cards:
            return None

        # Exclure les versions Full du tirage normal
        normal_cards = [c for c in cards if "(Full)" not in c['name']]
        if not normal_cards:
            return None

        card = random.choice(normal_cards)
        return (category, card['name'], card['id'])

    def draw_cards(self, count: int = 3) -> List[Tuple[str, str, str]]:
        """
        Tire un nombre de cartes aléatoires
        Returns: Liste de (category, name, file_id)
        """
        drawn = []
        attempts = 0
        max_attempts = count * 10  # Éviter les boucles infinies

        while len(drawn) < count and attempts < max_attempts:
            category = self._select_random_category()
            card = self._select_random_card(category)

            if card:
                drawn.append(card)

            attempts += 1

        return drawn

    def perform_daily_draw(self, user_id: str, username: str) -> Tuple[bool, List[dict], str]:
        """
        Effectue le tirage journalier d'un utilisateur
        Returns: (success, cards_drawn, message)
        """
        # Vérifier si le tirage est possible
        if not self.storage.can_perform_daily_draw(user_id):
            return (False, [], "Tu as déjà fait ton tirage journalier aujourd'hui !")

        # Réserver le tirage
        if not self.storage.record_daily_draw(user_id):
            return (False, [], "Erreur lors de l'enregistrement du tirage")

        # Effectuer le tirage
        drawn_cards = self.draw_cards(3)

        if not drawn_cards:
            return (False, [], "Erreur lors du tirage des cartes")

        results = []
        for category, name, file_id in drawn_cards:
            # Vérifier si c'est une nouvelle découverte
            is_new_discovery = not self.storage.is_card_discovered(category, name)

            if is_new_discovery:
                discovery_index = self.storage.log_discovery(category, name, user_id, username)
            else:
                discovery_index = None

            # Ajouter la carte à l'inventaire
            self.storage.add_card_to_user(user_id, category, name)

            results.append({
                "category": category,
                "name": name,
                "file_id": file_id,
                "is_new_discovery": is_new_discovery,
                "discovery_index": discovery_index,
                "is_full": False,
            })

        return (True, results, "Tirage effectué avec succès !")

    def perform_bonus_draw(self, user_id: str, username: str) -> Tuple[bool, List[dict], str]:
        """
        Effectue un tirage bonus
        Returns: (success, cards_drawn, message)
        """
        # Vérifier si l'utilisateur a des bonus
        bonus_count = self.storage.get_user_bonus_count(user_id)
        if bonus_count <= 0:
            return (False, [], "Tu n'as pas de tirage bonus disponible !")

        # Utiliser un bonus
        if not self.storage.use_bonus_draw(user_id):
            return (False, [], "Erreur lors de l'utilisation du bonus")

        # Effectuer le tirage (3 cartes comme le tirage normal)
        drawn_cards = self.draw_cards(3)

        if not drawn_cards:
            return (False, [], "Erreur lors du tirage des cartes")

        results = []
        for category, name, file_id in drawn_cards:
            is_new_discovery = not self.storage.is_card_discovered(category, name)

            if is_new_discovery:
                discovery_index = self.storage.log_discovery(category, name, user_id, username)
            else:
                discovery_index = None

            self.storage.add_card_to_user(user_id, category, name)

            results.append({
                "category": category,
                "name": name,
                "file_id": file_id,
                "is_new_discovery": is_new_discovery,
                "discovery_index": discovery_index,
                "is_full": False,
            })

        return (True, results, f"Tirage bonus effectué ! ({bonus_count - 1} bonus restants)")

    def perform_sacrificial_draw(
        self, user_id: str, username: str, selected_cards: List[Tuple[str, str]]
    ) -> Tuple[bool, List[dict], str]:
        """
        Effectue un tirage sacrificiel
        L'utilisateur sacrifie 5 cartes pour en tirer 3 nouvelles

        Args:
            user_id: ID de l'utilisateur
            username: Nom de l'utilisateur
            selected_cards: Liste des 5 cartes à sacrifier [(category, name), ...]

        Returns: (success, cards_drawn, message)
        """
        # Vérifier si le tirage sacrificiel est possible aujourd'hui
        if not self.storage.can_perform_sacrificial_draw(user_id):
            return (False, [], "Tu as déjà fait ton tirage sacrificiel aujourd'hui !")

        # Vérifier que 5 cartes sont sélectionnées
        if len(selected_cards) != 5:
            return (False, [], "Tu dois sélectionner exactement 5 cartes à sacrifier !")

        # Vérifier que les cartes sélectionnées correspondent aux cartes sacrificielles du jour
        daily_sacrificial = self.storage.get_sacrificial_cards(user_id)
        if not daily_sacrificial:
            return (False, [], "Tu n'as pas assez de cartes pour un tirage sacrificiel !")

        # Vérifier que toutes les cartes sélectionnées sont dans la liste autorisée
        for card in selected_cards:
            if card not in daily_sacrificial:
                return (False, [], f"La carte {card[1]} n'est pas dans ta sélection sacrificielle du jour !")

        # Vérifier que l'utilisateur possède toutes les cartes
        for category, name in selected_cards:
            if self.storage.get_user_card_count(user_id, category, name) < 1:
                return (False, [], f"Tu ne possèdes pas la carte {name} !")

        # Retirer les cartes sacrifiées
        for category, name in selected_cards:
            if not self.storage.remove_card_from_user(user_id, category, name):
                # Rollback des cartes déjà retirées
                for prev_cat, prev_name in selected_cards:
                    if (prev_cat, prev_name) == (category, name):
                        break
                    self.storage.add_card_to_user(user_id, prev_cat, prev_name)
                return (False, [], "Erreur lors du sacrifice des cartes")

        # Enregistrer le tirage sacrificiel
        if not self.storage.record_sacrificial_draw(user_id):
            # Rollback
            for category, name in selected_cards:
                self.storage.add_card_to_user(user_id, category, name)
            return (False, [], "Erreur lors de l'enregistrement du tirage")

        # Effectuer le tirage (3 cartes)
        drawn_cards = self.draw_cards(3)

        if not drawn_cards:
            return (False, [], "Erreur lors du tirage des cartes")

        results = []
        for category, name, file_id in drawn_cards:
            is_new_discovery = not self.storage.is_card_discovered(category, name)

            if is_new_discovery:
                discovery_index = self.storage.log_discovery(category, name, user_id, username)
            else:
                discovery_index = None

            self.storage.add_card_to_user(user_id, category, name)

            results.append({
                "category": category,
                "name": name,
                "file_id": file_id,
                "is_new_discovery": is_new_discovery,
                "discovery_index": discovery_index,
                "is_full": False,
            })

        return (True, results, "Tirage sacrificiel effectué avec succès !")

    def get_draw_status(self, user_id: str) -> dict:
        """Retourne le statut des tirages disponibles pour un utilisateur"""
        can_daily = self.storage.can_perform_daily_draw(user_id)
        bonus_count = self.storage.get_user_bonus_count(user_id)
        can_sacrificial = self.storage.can_perform_sacrificial_draw(user_id)
        sacrificial_cards = self.storage.get_sacrificial_cards(user_id) if can_sacrificial else []

        return {
            "can_daily_draw": can_daily,
            "bonus_available": bonus_count,
            "can_sacrificial_draw": can_sacrificial and len(sacrificial_cards) >= 5,
            "sacrificial_cards": [
                {"category": cat, "name": name}
                for cat, name in sacrificial_cards
            ] if sacrificial_cards else [],
        }


# Instance singleton
_drawing_service: Optional[DrawingService] = None


def get_drawing_service() -> DrawingService:
    """Retourne l'instance singleton du service de tirage"""
    global _drawing_service
    if _drawing_service is None:
        _drawing_service = DrawingService()
    return _drawing_service
