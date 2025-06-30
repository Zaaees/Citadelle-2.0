"""
Logique de tirage des cartes.
Gère les tirages aléatoires, sacrificiels, et journaliers.
"""

import random
import hashlib
import logging
from datetime import datetime
import pytz
from typing import List, Tuple, Dict, Any

from .config import RARITY_WEIGHTS, ALL_CATEGORIES, DAILY_SACRIFICIAL_CARDS_COUNT
from .storage import CardsStorage


class DrawingManager:
    """Gestionnaire des tirages de cartes."""
    
    def __init__(self, storage: CardsStorage, cards_by_category: Dict[str, List[Dict]],
                 upgrade_cards_by_category: Dict[str, List[Dict]]):
        self.storage = storage
        self.cards_by_category = cards_by_category
        self.upgrade_cards_by_category = upgrade_cards_by_category
    
    def draw_cards(self, number: int) -> List[Tuple[str, str]]:
        """
        Effectue un tirage aléatoire de `number` cartes avec rareté adaptative.
        Ne tire que des cartes normales (pas de cartes Full).
        Les cartes Full ne peuvent être obtenues que par échange de 5 cartes normales.

        Args:
            number: Nombre de cartes à tirer

        Returns:
            List[Tuple[str, str]]: Liste des cartes tirées (category, name)
        """
        drawn = []

        # Définir les catégories disponibles
        available_categories = ALL_CATEGORIES
        category_weights = [RARITY_WEIGHTS[cat] for cat in available_categories]

        for _ in range(number):
            # Sélection de la catégorie selon les poids de rareté
            category = random.choices(available_categories, weights=category_weights)[0]

            # Sélection aléatoire d'une carte dans la catégorie
            available_cards = self.cards_by_category.get(category, [])
            if not available_cards:
                continue

            selected_card = random.choice(available_cards)
            card_name = selected_card['name'].removesuffix('.png')

            # Ajouter uniquement la carte normale (pas de variante Full)
            drawn.append((category, card_name))

        return drawn

    
    def select_daily_sacrificial_cards(self, user_id: int, eligible_cards: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
        """
        Sélectionne 5 cartes de manière déterministe basée sur le jour actuel et l'ID utilisateur.
        La sélection reste la même pour un utilisateur donné pendant toute la journée.
        Gère intelligemment les doublons pour éviter de sélectionner plus de cartes d'un type que l'utilisateur n'en possède.
        
        Args:
            user_id: ID de l'utilisateur
            eligible_cards: Liste des cartes éligibles (category, name)
        
        Returns:
            List[Tuple[str, str]]: Liste des cartes sélectionnées
        """
        # Obtenir la date actuelle en timezone Paris
        paris_tz = pytz.timezone("Europe/Paris")
        today = datetime.now(paris_tz).strftime("%Y-%m-%d")
        
        # Créer une seed déterministe basée sur l'utilisateur et le jour
        seed_string = f"{user_id}-{today}"
        seed = int(hashlib.md5(seed_string.encode()).hexdigest(), 16) % (2**32)
        
        # Utiliser cette seed pour la sélection
        rng = random.Random(seed)
        
        # Compter les occurrences de chaque carte unique
        card_counts = {}
        for card in eligible_cards:
            card_counts[card] = card_counts.get(card, 0) + 1
        
        # Créer une liste pondérée où chaque carte apparaît selon son nombre d'exemplaires
        weighted_cards = []
        for card, count in card_counts.items():
            weighted_cards.extend([card] * count)
        
        # Sélectionner jusqu'à 5 cartes uniques
        selected = []
        selected_set = set()
        attempts = 0
        max_attempts = len(weighted_cards) * 2  # Éviter les boucles infinies
        
        while len(selected) < DAILY_SACRIFICIAL_CARDS_COUNT and attempts < max_attempts:
            if not weighted_cards:
                break
            
            card = rng.choice(weighted_cards)
            if card not in selected_set:
                selected.append(card)
                selected_set.add(card)
            
            attempts += 1
        
        return selected
    
    def can_perform_daily_draw(self, user_id: int) -> bool:
        """
        Vérifie si un utilisateur peut effectuer son tirage journalier.
        Optimisé avec cache pour réduire les appels Google Sheets.

        Args:
            user_id: ID de l'utilisateur

        Returns:
            bool: True si le tirage est autorisé
        """
        try:
            paris_tz = pytz.timezone("Europe/Paris")
            today = datetime.now(paris_tz).strftime("%Y-%m-%d")
            user_id_str = str(user_id)

            # Utiliser le cache pour éviter les appels répétés
            cache_key = f"daily_draw_{user_id}_{today}"
            if hasattr(self, '_daily_draw_cache'):
                if cache_key in self._daily_draw_cache:
                    return self._daily_draw_cache[cache_key]
            else:
                self._daily_draw_cache = {}

            # Vérifier dans la feuille des tirages journaliers
            all_rows = self.storage.sheet_daily_draw.get_all_values()
            row_idx = next((i for i, r in enumerate(all_rows) if r and r[0] == user_id_str), None)

            can_draw = True
            if row_idx is not None and len(all_rows[row_idx]) > 1 and all_rows[row_idx][1] == today:
                can_draw = False  # Déjà tiré aujourd'hui

            # Mettre en cache le résultat
            self._daily_draw_cache[cache_key] = can_draw
            return can_draw

        except Exception as e:
            logging.error(f"[DRAWING] Erreur lors de la vérification du tirage journalier: {e}")
            return False
    
    def record_daily_draw(self, user_id: int) -> bool:
        """
        Enregistre qu'un utilisateur a effectué son tirage journalier.
        Optimisé avec invalidation du cache.

        Args:
            user_id: ID de l'utilisateur

        Returns:
            bool: True si l'enregistrement a réussi
        """
        try:
            paris_tz = pytz.timezone("Europe/Paris")
            today = datetime.now(paris_tz).strftime("%Y-%m-%d")
            user_id_str = str(user_id)

            # Mettre à jour ou ajouter l'entrée
            all_rows = self.storage.sheet_daily_draw.get_all_values()
            row_idx = next((i for i, r in enumerate(all_rows) if r and r[0] == user_id_str), None)

            if row_idx is not None:
                # Mettre à jour la ligne existante
                self.storage.sheet_daily_draw.update(f"B{row_idx + 1}", today)
            else:
                # Ajouter une nouvelle ligne
                self.storage.sheet_daily_draw.append_row([user_id_str, today])

            # Invalider le cache pour cet utilisateur APRÈS l'enregistrement
            if hasattr(self, '_daily_draw_cache'):
                cache_key = f"daily_draw_{user_id}_{today}"
                self._daily_draw_cache[cache_key] = False
                # Aussi invalider toutes les entrées de cache pour cet utilisateur
                keys_to_remove = [k for k in self._daily_draw_cache.keys() if k.startswith(f"daily_draw_{user_id}_")]
                for k in keys_to_remove:
                    del self._daily_draw_cache[k]

            # Marquer que cet utilisateur a besoin d'une vérification d'upgrade via le cog principal
            if hasattr(self.storage, '_cog_ref'):
                self.storage._cog_ref._mark_user_for_upgrade_check(user_id)

            logging.info(f"[DRAWING] Tirage journalier enregistré pour l'utilisateur {user_id}")
            return True

        except Exception as e:
            logging.error(f"[DRAWING] Erreur lors de l'enregistrement du tirage journalier: {e}")
            return False

    def can_perform_sacrificial_draw(self, user_id: int) -> bool:
        """
        Vérifie si un utilisateur peut effectuer son tirage sacrificiel.
        Optimisé avec cache pour réduire les appels Google Sheets.

        Args:
            user_id: ID de l'utilisateur

        Returns:
            bool: True si le tirage est autorisé
        """
        try:
            paris_tz = pytz.timezone("Europe/Paris")
            today = datetime.now(paris_tz).strftime("%Y-%m-%d")
            user_id_str = str(user_id)

            # Utiliser le cache pour éviter les appels répétés
            cache_key = f"sacrificial_draw_{user_id}_{today}"
            if hasattr(self, '_sacrificial_draw_cache'):
                if cache_key in self._sacrificial_draw_cache:
                    return self._sacrificial_draw_cache[cache_key]
            else:
                self._sacrificial_draw_cache = {}

            # Vérifier dans la feuille des tirages sacrificiels
            all_rows = self.storage.sheet_sacrificial_draw.get_all_values()
            row_idx = next((i for i, r in enumerate(all_rows) if r and r[0] == user_id_str), None)

            can_draw = True
            if row_idx is not None and len(all_rows[row_idx]) > 1 and all_rows[row_idx][1] == today:
                can_draw = False  # Déjà tiré aujourd'hui

            # Mettre en cache le résultat
            self._sacrificial_draw_cache[cache_key] = can_draw
            return can_draw

        except Exception as e:
            logging.error(f"[DRAWING] Erreur lors de la vérification du tirage sacrificiel: {e}")
            return False

    def record_sacrificial_draw(self, user_id: int) -> bool:
        """
        Enregistre qu'un utilisateur a effectué son tirage sacrificiel.
        Optimisé avec invalidation du cache.

        Args:
            user_id: ID de l'utilisateur

        Returns:
            bool: True si l'enregistrement a réussi
        """
        try:
            paris_tz = pytz.timezone("Europe/Paris")
            today = datetime.now(paris_tz).strftime("%Y-%m-%d")
            user_id_str = str(user_id)

            # Mettre à jour ou ajouter l'entrée
            all_rows = self.storage.sheet_sacrificial_draw.get_all_values()
            row_idx = next((i for i, r in enumerate(all_rows) if r and r[0] == user_id_str), None)

            if row_idx is not None:
                # Mettre à jour la ligne existante
                self.storage.sheet_sacrificial_draw.update(f"B{row_idx + 1}", today)
            else:
                # Ajouter une nouvelle ligne
                self.storage.sheet_sacrificial_draw.append_row([user_id_str, today])

            # Invalider le cache pour cet utilisateur APRÈS l'enregistrement
            if hasattr(self, '_sacrificial_draw_cache'):
                cache_key = f"sacrificial_draw_{user_id}_{today}"
                self._sacrificial_draw_cache[cache_key] = False
                # Aussi invalider toutes les entrées de cache pour cet utilisateur
                keys_to_remove = [k for k in self._sacrificial_draw_cache.keys() if k.startswith(f"sacrificial_draw_{user_id}_")]
                for k in keys_to_remove:
                    del self._sacrificial_draw_cache[k]

            # Marquer que cet utilisateur a besoin d'une vérification d'upgrade via le cog principal
            if hasattr(self.storage, '_cog_ref'):
                self.storage._cog_ref._mark_user_for_upgrade_check(user_id)

            logging.info(f"[DRAWING] Tirage sacrificiel enregistré pour l'utilisateur {user_id}")
            return True

        except Exception as e:
            logging.error(f"[DRAWING] Erreur lors de l'enregistrement du tirage sacrificiel: {e}")
            return False

    def clear_sacrificial_cache(self, user_id: int = None):
        """
        Nettoie le cache du tirage sacrificiel.

        Args:
            user_id: Si spécifié, nettoie seulement le cache de cet utilisateur.
                    Sinon, nettoie tout le cache.
        """
        if not hasattr(self, '_sacrificial_draw_cache'):
            return

        if user_id is not None:
            # Nettoyer seulement pour cet utilisateur
            keys_to_remove = [k for k in self._sacrificial_draw_cache.keys()
                             if k.startswith(f"sacrificial_draw_{user_id}_")]
            for k in keys_to_remove:
                del self._sacrificial_draw_cache[k]
            logging.info(f"[DRAWING] Cache sacrificiel nettoyé pour l'utilisateur {user_id}")
        else:
            # Nettoyer tout le cache
            self._sacrificial_draw_cache.clear()
            logging.info("[DRAWING] Cache sacrificiel entièrement nettoyé")


