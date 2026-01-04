"""
Service principal pour le système de cartes.
Bridge entre le Root Storage (Site/backend/storage.py) et les Managers du Bot (cogs/cards/).
"""

import sys
import os
import logging
from typing import List, Dict, Any, Optional, Tuple
import asyncio

# Ajouter le chemin vers le code du bot
BOT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../'))
sys.path.insert(0, BOT_PATH)

# Importer les managers du bot
from cogs.cards.drawing import DrawingManager
from cogs.cards.trading import TradingManager
from cogs.cards.vault import VaultManager
from cogs.cards.config import ALL_CATEGORIES, RARITY_WEIGHTS
from cogs.cards.utils import normalize_name

# Importer le Root Storage
logger = logging.getLogger(__name__)

# Tenter d'importer le storage global
try:
    # On assume que le current working directory permet cet import ou que sys.path est correct
    # Si on est lancé depuis root, 'Site.backend.storage' ou 'backend.storage'
    from ...storage import get_storage_service, CardsStorageService
except ImportError:
    # Fallback si on est dans un autre contexte
    try:
        from Site.backend.storage import get_storage_service, CardsStorageService
    except ImportError:
        logger.error("❌ Impossible d'importer CardsStorageService depuis backend.storage")
        # On ne raise pas ici pour laisser initialize() gérer si besoin, mais ça va probablement crash plus tard
        pass

# Seuil de conversion (5 cartes normales → 1 Full) pour toutes les catégories
UPGRADE_THRESHOLD = 5


class CardSystemService:
    """
    Service singleton pour accéder au système de cartes.
    Utilise CardsStorageService (Root) pour la persistence, et les Managers du Bot pour la logique de jeu.
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialise le service (une seule fois grâce au singleton)."""
        pass

    def initialize(self):
        """Initialise la connexion Google Sheets et les managers."""
        if not CardSystemService._initialized:
            self._initialize_internal()
            CardSystemService._initialized = True

    def _initialize_internal(self):
        """Initialise les composants."""
        logger.info("🔄 Initialisation du CardSystemService (Unified Mode)...")

        try:
            # 1. Récupérer le storage singleton (Root)
            self.storage = get_storage_service()
            logger.info("✅ Storage Service connecté")

            # 2. Récupérer les données de cartes du storage
            # Root storage charge les cartes à l'init
            self.cards_by_category = self.storage.get_all_cards()
            self.upgrade_cards_by_category = self.storage.get_all_full_cards()

            # 3. Initialiser les Managers (Logic Layer) en leur passant le Storage (Data Layer)
            # DrawingManager: besoin de storage (can_daily_draw, etc.) + cards data
            self.drawing_manager = DrawingManager(
                self.storage,
                self.cards_by_category,
                self.upgrade_cards_by_category
            )
            
            # VaultManager: besoin de storage (add_to_vault, etc.)
            self.vault_manager = VaultManager(self.storage)

            # TradingManager: besoin de storage (exchange sheet) + vault manager
            # On lui passe self.storage qui a maintenant les méthodes exchange portées
            self.trading_manager = TradingManager(
                self.storage,
                self.vault_manager
            )

            # 4. Injecter les méthodes de compatibilité dans le trading manager
            # TradingManager (du bot) attend _user_has_card, _add_card_to_user, _remove_card_from_user sur 'bot.cards_cog' (ou similaire)
            # Ici il prend self.storage comme 'cog' ou 'storage'?
            # Check TradingManager.__init__: self.storage = storage.
            # Il appelle self._user_has_card ? Non il appelle self.storage.xxx ?
            # Vérifions cogs/cards/trading.py:
            # Il fait: `if not self._user_has_card(request['owner'], request['cat'], request['name']):`
            # Et: `self._user_has_card = None` dans init.
            # Donc il faut injecter.
            
            self.trading_manager._user_has_card = self._user_has_card
            self.trading_manager._add_card_to_user = self._add_card_to_user
            self.trading_manager._remove_card_from_user = self._remove_card_from_user

            logger.info("✅ CardSystemService et Managers initialisés avec succès")

        except Exception as e:
            logger.error(f"❌ Erreur critique lors de l'initialisation du CardSystemService: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise e

    # ----------------------------------------------------------------
    # Compatibilité / Proxy vers Storage
    # ----------------------------------------------------------------

    def _user_has_card(self, user_id: int, category: str, name: str) -> bool:
        """Vérifie si un utilisateur possède une carte."""
        return self.storage.get_user_card_count(str(user_id), category, name) > 0

    def _add_card_to_user(self, user_id: int, category: str, name: str) -> bool:
        """Ajoute une carte à l'utilisateur."""
        return self.storage.add_card_to_user(str(user_id), category, name)

    def _remove_card_from_user(self, user_id: int, category: str, name: str) -> bool:
        """Retire une carte à l'utilisateur."""
        return self.storage.remove_card_from_user(str(user_id), category, name)

    # ----------------------------------------------------------------
    # Logique de Conversion (Upgrade)
    # ----------------------------------------------------------------

    def check_and_upgrade_cards(self, user_id: int) -> List[Dict[str, Any]]:
        """
        Vérifie si l'utilisateur a 5 cartes identiques pour les convertir en Full.
        Réimplémenté ici car le Root Storage n'a pas cette logique métier.
        """
        upgraded_cards = []
        try:
            # Récupérer les cartes brutes du storage
            user_cards_tuples = self.storage.get_user_cards(str(user_id))
            
            # Convertir en liste plate pour compter
            user_cards_flat = []
            for cat, name, count in user_cards_tuples:
                user_cards_flat.extend([(cat, name)] * count)

            from collections import Counter
            card_counts = Counter(user_cards_flat)
            
            for (category, name), count in card_counts.items():
                if "(Full)" in name:
                    continue
                
                if count >= UPGRADE_THRESHOLD:
                    full_name = f"{name} (Full)"
                    
                    # Vérifier si possède déjà la Full (si unique)
                    if self._user_has_card(user_id, category, full_name):
                        continue
                        
                    full_card_info = self._find_full_card(category, name)
                    if not full_card_info:
                        continue

                    # Tenter la conversion
                    # 1. Retirer 5 cartes
                    removed_count = 0
                    success_remove = True
                    for _ in range(UPGRADE_THRESHOLD):
                        if self._remove_card_from_user(user_id, category, name):
                            removed_count += 1
                        else:
                            success_remove = False
                            break
                    
                    if not success_remove:
                        # Rollback partiel
                        for _ in range(removed_count):
                            self._add_card_to_user(user_id, category, name)
                        continue

                    # 2. Ajouter la Full
                    if self._add_card_to_user(user_id, category, full_name):
                        logger.info(f"UPGRADE: {user_id} a obtenu {full_name}")
                        upgraded_cards.append({
                            "category": category,
                            "name": full_name,
                            "file_id": full_card_info.get("file_id"),
                            "sacrificed_count": UPGRADE_THRESHOLD,
                            "original_name": name
                        })
                    else:
                        # Rollback total
                        for _ in range(UPGRADE_THRESHOLD):
                            self._add_card_to_user(user_id, category, name)

            return upgraded_cards
            
        except Exception as e:
            logger.error(f"Erreur upgrades: {e}")
            return []

    def _find_full_card(self, category: str, base_name: str) -> Optional[Dict[str, Any]]:
        full_name = f"{base_name} (Full)"
        for card in self.upgrade_cards_by_category.get(category, []):
            card_name = card["name"].removesuffix(".png")
            if normalize_name(card_name) == normalize_name(full_name):
                return card
        # Fallback autres catégories
        for search_cat, full_cards in self.upgrade_cards_by_category.items():
            if search_cat == category:
                continue
            for card in full_cards:
                card_name = card["name"].removesuffix(".png")
                if normalize_name(card_name) == normalize_name(full_name):
                    return card
        return None

    # ----------------------------------------------------------------
    # API Data Formatters
    # ----------------------------------------------------------------

    async def get_user_collection(self, user_id: int) -> Dict[str, Any]:
        """
        Adapte le format du Root Storage (tuples) vers le format attendu par l'API (dict).
        """
        try:
            # Récupérer les données brutes
            user_cards_tuples = await asyncio.to_thread(self.storage.get_user_cards, str(user_id))

            user_cards = []
            total_cards = 0
            unique_cards = 0
            unique_full_cards = 0

            for category, name, count in user_cards_tuples:
                is_full = "(Full)" in name

                # Retrouver file_id
                file_id = None
                target_list = self.upgrade_cards_by_category if is_full else self.cards_by_category
                # Optim: lookup map could be built once, but list loop is okay for now
                for card in target_list.get(category, []):
                    if card["name"] == name:
                        file_id = card.get("file_id")
                        break
                
                user_cards.append({
                    "category": category,
                    "name": name,
                    "count": count,
                    "acquired_date": "",
                    "file_id": file_id,
                    "is_full": is_full
                })

                total_cards += count
                if is_full:
                    unique_full_cards += 1
                else:
                    unique_cards += 1

            # Calculs stats
            total_available_cards = sum(len(self.cards_by_category.get(c, [])) for c in ALL_CATEGORIES)
            completion = (unique_cards / total_available_cards * 100) if total_available_cards > 0 else 0.0

            return {
                "cards": user_cards,
                "total_cards": total_cards,
                "unique_cards": unique_cards,
                "unique_full_cards": unique_full_cards,
                "completion_percentage": round(completion, 2)
            }

        except Exception as e:
            logger.error(f"❌ Erreur lors de la récupération de la collection: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {"cards": [], "total_cards": 0, "unique_cards": 0, "completion_percentage": 0.0}

    async def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        """Agrège les stats depuis le storage."""
        try:
            collection = await self.get_user_collection(user_id)
            
            # Cards by rarity
            cards_by_rarity = {}
            for cat in ALL_CATEGORIES:
                count = 0
                for c in collection["cards"]:
                    if c["category"] == cat and not c["is_full"]:
                        count += 1 # Compte items uniques ou total? API seems to expect unique count usually, strictly collection items
                        # Site/frontend/src/pages/Home.tsx usage? Usually purely informational.
                        # Using unique count as per previous implementation logic usually
                cards_by_rarity[cat] = count

            # Calculs dispos
            bonus_count = self.storage.get_user_bonus_count(str(user_id))
            
            # Utiliser DrawingManager pour la logique "check only" si possible, 
            # ou appeler storage directement. DrawingManager.can_perform_daily... appelle storage.
            # Mais DrawingManager a peut-etre "check_only" param?
            # DrawingManager: def can_perform_daily_draw(self, user_id, check_only=False)
            can_daily = self.drawing_manager.can_perform_daily_draw(user_id, check_only=True)
            can_sacrificial = self.drawing_manager.can_perform_sacrificial_draw(user_id)
            
            # Weekly exchanges
            weekly_used = self.storage.get_weekly_trades_count(str(user_id))
            
            # Discoveries
            # count_user_discoveries n'existe pas dans Root storage ?
            # Root storage a get_discovered_cards() -> Set of (cat, name). 
            # Mais ça c'est GLOBAL.
            # On veut les découvertes DU USER?
            # Root storage: log_discovery(..., user_id, ...).
            # Mais pas de méthode get_user_discoveries_count efficiente.
            # On peut scanner get_all_values("Découvertes") ?
            # Couteux. Mais "CardsStorageService.log_discovery" écrit dans "Découvertes".
            # Le Root Storage ne semble pas avoir de méthode optimisée pour compter les découvertes par user.
            # On va faire 0 pour l'instant ou implémenter un scan simple si critique.
            discoveries_count = 0 
            # TODO: Implémenter count discoveries dans storage si nécessaire

            total_available = sum(len(self.cards_by_category.get(c, [])) for c in ALL_CATEGORIES)
            available_by_category = {c: len(self.cards_by_category.get(c, [])) for c in ALL_CATEGORIES}

            return {
                "total_cards": collection["total_cards"],
                "unique_cards": collection["unique_cards"],
                "full_cards": collection["unique_full_cards"],
                "completion_percentage": collection["completion_percentage"],
                "total_available_cards": total_available,
                "cards_by_rarity": cards_by_rarity,
                "available_by_category": available_by_category,
                "bonus_available": bonus_count,
                "can_daily_draw": can_daily,
                "can_sacrificial_draw": can_sacrificial,
                "weekly_exchanges_used": weekly_used,
                "weekly_exchanges_remaining": 3 - weekly_used,
                "discoveries_count": discoveries_count
            }
        except Exception as e:
             logger.error(f"Error getting user stats: {e}")
             return {}

    # ----------------------------------------------------------------
    # Proxy Methods
    # ----------------------------------------------------------------

    def get_all_cards(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """Proxy vers storage cards."""
        all_cards = []
        cats = [category] if category else ALL_CATEGORIES
        
        for c in cats:
            for card in self.cards_by_category.get(c, []):
                 all_cards.append({**card, "is_full": False, "rarity_weight": RARITY_WEIGHTS.get(c, 0)})
            for card in self.upgrade_cards_by_category.get(c, []):
                 all_cards.append({**card, "is_full": True, "rarity_weight": RARITY_WEIGHTS.get(c, 0)})
        return all_cards

    def get_categories_info(self) -> List[Dict[str, Any]]:
        infos = []
        total = sum(len(self.cards_by_category.get(c, [])) for c in ALL_CATEGORIES)
        for c in ALL_CATEGORIES:
            count = len(self.cards_by_category.get(c, []))
            infos.append({
                "category": c,
                "weight": RARITY_WEIGHTS.get(c, 0),
                "total_cards": count,
                "percentage": (count / total * 100) if total else 0
            })
        return infos

    def consume_user_bonus(self, user_id: int) -> bool:
        return self.storage.use_bonus_draw(str(user_id))
        
    def get_user_bonus_count(self, user_id: int) -> int:
        """Retourne le nombre de bonus disponibles pour un utilisateur."""
        return self.storage.get_user_bonus_count(str(user_id))

    def get_username(self, user_id: int) -> Optional[str]:
        """
        Tente de récupérer le nom d'utilisateur.
        """
        # Pour l'instant on retourne None, le front utilisera User_ID
        # On pourrait implémenter un cache ou lookup si on avait accès à la DB discord ou user cache
        return None

# Instance globale pour l'API
card_system = CardSystemService()
