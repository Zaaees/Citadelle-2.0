"""
Système de découverte des cartes.
Gère l'enregistrement et le suivi des découvertes de cartes.
"""

import time
import logging
from datetime import datetime
import pytz
from typing import Set, Tuple, Optional

from .storage import CardsStorage


class DiscoveryManager:
    """Gestionnaire des découvertes de cartes."""
    
    def __init__(self, storage: CardsStorage):
        self.storage = storage
    
    def get_discovered_cards(self) -> Set[Tuple[str, str]]:
        """Récupère toutes les cartes découvertes depuis le cache."""
        discoveries_cache = self.storage.get_discoveries_cache()
        
        if not discoveries_cache:
            return set()
        
        discovered = set()
        for row in discoveries_cache[1:]:  # Skip header
            if len(row) >= 2:
                discovered.add((row[0], row[1]))  # (category, name)
        return discovered
    
    def log_discovery(self, category: str, name: str, discoverer_id: int, discoverer_name: str) -> int:
        """
        Enregistre une nouvelle découverte et retourne l'index de découverte.
        
        Args:
            category: Catégorie de la carte
            name: Nom de la carte
            discoverer_id: ID Discord du découvreur
            discoverer_name: Nom d'affichage du découvreur
        
        Returns:
            int: Index de découverte (numéro chronologique)
        """
        with self.storage._discoveries_lock:
            try:
                # Rafraîchir le cache si nécessaire
                discoveries_cache = self.storage.get_discoveries_cache()
                
                # Vérifier si la carte n'est pas déjà découverte
                if discoveries_cache:
                    for row in discoveries_cache[1:]:  # Skip header
                        if len(row) >= 6 and row[0] == category and row[1] == name:
                            return int(row[5])  # Retourner l'index existant
                
                # Calculer le nouvel index de découverte
                discovery_index = len(discoveries_cache) if discoveries_cache else 1
                
                # Timestamp actuel
                paris_tz = pytz.timezone("Europe/Paris")
                timestamp = datetime.now(paris_tz).strftime("%Y-%m-%d %H:%M:%S")
                
                # Ajouter la nouvelle découverte
                new_row = [
                    category, name, str(discoverer_id), discoverer_name,
                    timestamp, str(discovery_index)
                ]
                
                self.storage.sheet_discoveries.append_row(new_row)
                self.storage.refresh_discoveries_cache()
                
                logging.info(f"[DISCOVERY] Nouvelle découverte enregistrée: {name} ({category}) par {discoverer_name} (index: {discovery_index})")
                return discovery_index
                
            except Exception as e:
                logging.error(f"[DISCOVERY] Erreur lors de l'enregistrement de la découverte: {e}")
                return 0
    
    def is_card_discovered(self, category: str, name: str) -> bool:
        """Vérifie si une carte a déjà été découverte."""
        discovered_cards = self.get_discovered_cards()
        return (category, name) in discovered_cards
    
    def get_discovery_info(self, category: str, name: str) -> Optional[dict]:
        """
        Récupère les informations de découverte d'une carte.
        
        Returns:
            dict: Informations de découverte ou None si non trouvée
        """
        discoveries_cache = self.storage.get_discoveries_cache()
        
        if not discoveries_cache:
            return None
        
        for row in discoveries_cache[1:]:  # Skip header
            if len(row) >= 6 and row[0] == category and row[1] == name:
                return {
                    'category': row[0],
                    'name': row[1],
                    'discoverer_id': int(row[2]),
                    'discoverer_name': row[3],
                    'timestamp': row[4],
                    'discovery_index': int(row[5])
                }
        
        return None
    
    def get_discovery_stats(self) -> dict:
        """
        Retourne les statistiques de découverte.
        
        Returns:
            dict: Statistiques avec total_all, discovered_all, etc.
        """
        # Cette méthode sera implémentée avec les données des cartes disponibles
        # Pour l'instant, retourne des valeurs par défaut
        return {
            'total_all': 0,
            'discovered_all': 0,
            'remaining_all': 0,
            'total_no_full': 0,
            'discovered_no_full': 0,
            'remaining_no_full': 0
        }
