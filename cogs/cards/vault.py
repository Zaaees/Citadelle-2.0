"""
Gestion du système de vault pour les échanges de cartes.
"""

import logging
from typing import List, Tuple, Optional

from .storage import CardsStorage
from .utils import validate_card_data, is_full_card, merge_cells


class VaultManager:
    """Gestionnaire du système de vault."""
    
    def __init__(self, storage: CardsStorage):
        self.storage = storage
    
    def add_card_to_vault(self, user_id: int, category: str, name: str, 
                         skip_possession_check: bool = False) -> bool:
        """
        Ajoute une carte au vault d'un utilisateur.
        
        Args:
            user_id: ID de l'utilisateur
            category: Catégorie de la carte
            name: Nom de la carte
            skip_possession_check: Ignorer la vérification de possession
        
        Returns:
            bool: True si succès
        """
        with self.storage._vault_lock:
            try:
                # Validation des paramètres d'entrée
                if not validate_card_data(category, name, user_id):
                    return False
                
                # RESTRICTION: Empêcher le dépôt de cartes Full dans le vault
                if is_full_card(name):
                    logging.error(f"[SECURITY] Tentative de dépôt d'une carte Full dans le vault: user_id={user_id}, carte=({category}, {name})")
                    return False
                
                vault_cache = self.storage.get_vault_cache()
                if not vault_cache:
                    return False
                
                # Chercher si la carte existe déjà dans le vault
                for i, row in enumerate(vault_cache):
                    if len(row) >= 2 and row[0] == category and row[1] == name:
                        # Carte trouvée, ajouter l'utilisateur ou incrémenter
                        original_len = len(row)
                        for j, cell in enumerate(row[2:], start=2):
                            if not cell:
                                continue
                            try:
                                uid, count = cell.split(":", 1)
                                uid = uid.strip()
                                if int(uid) == user_id:
                                    # Utilisateur trouvé, incrémenter
                                    new_count = int(count) + 1
                                    row[j] = f"{user_id}:{new_count}"
                                    cleaned_row = merge_cells(row)
                                    pad = max(original_len, len(cleaned_row)) - len(cleaned_row)
                                    cleaned_row += [""] * pad
                                    self.storage.sheet_vault.update(f"A{i+1}", [cleaned_row])
                                    self.storage.refresh_vault_cache()
                                    logging.info(f"[VAULT] Carte incrémentée dans le vault: user_id={user_id}, carte=({category}, {name})")
                                    return True
                            except (ValueError, IndexError) as e:
                                logging.error(f"[SECURITY] Données corrompues dans add_card_to_vault: {cell}, erreur: {e}")
                                return False
                        
                        # Utilisateur pas trouvé, l'ajouter
                        row.append(f"{user_id}:1")
                        cleaned_row = merge_cells(row)
                        pad = max(original_len + 1, len(cleaned_row)) - len(cleaned_row)
                        cleaned_row += [""] * pad
                        self.storage.sheet_vault.update(f"A{i+1}", [cleaned_row])
                        self.storage.refresh_vault_cache()
                        logging.info(f"[VAULT] Nouvelle entrée ajoutée au vault: user_id={user_id}, carte=({category}, {name})")
                        return True
                
                # Si la carte n'existe pas encore dans le vault
                new_row = [category, name, f"{user_id}:1"]
                self.storage.sheet_vault.append_row(new_row)
                self.storage.refresh_vault_cache()
                logging.info(f"[VAULT] Nouvelle carte créée dans le vault: user_id={user_id}, carte=({category}, {name})")
                return True
                
            except Exception as e:
                logging.error(f"[VAULT] Erreur lors de l'ajout au vault: {e}")
                return False
    
    def remove_card_from_vault(self, user_id: int, category: str, name: str) -> bool:
        """
        Retire une carte du vault d'un utilisateur.
        
        Args:
            user_id: ID de l'utilisateur
            category: Catégorie de la carte
            name: Nom de la carte
        
        Returns:
            bool: True si succès
        """
        with self.storage._vault_lock:
            try:
                if not validate_card_data(category, name, user_id):
                    return False
                
                vault_cache = self.storage.get_vault_cache()
                if not vault_cache:
                    return False
                
                for i, row in enumerate(vault_cache):
                    if len(row) >= 2 and row[0] == category and row[1] == name:
                        original_len = len(row)
                        for j, cell in enumerate(row[2:], start=2):
                            if not cell:
                                continue
                            try:
                                uid, count = cell.split(":", 1)
                                uid = uid.strip()
                                if int(uid) == user_id:
                                    count = int(count)
                                    if count > 1:
                                        # Décrémenter
                                        row[j] = f"{user_id}:{count-1}"
                                    else:
                                        # Supprimer l'entrée
                                        row[j] = ""
                                    
                                    cleaned_row = merge_cells(row)
                                    pad = max(original_len, len(cleaned_row)) - len(cleaned_row)
                                    cleaned_row += [""] * pad
                                    self.storage.sheet_vault.update(f"A{i+1}", [cleaned_row])
                                    self.storage.refresh_vault_cache()
                                    logging.info(f"[VAULT] Carte retirée du vault: user_id={user_id}, carte=({category}, {name})")
                                    return True
                            except (ValueError, IndexError) as e:
                                logging.error(f"[SECURITY] Données corrompues dans remove_card_from_vault: {cell}, erreur: {e}")
                                continue
                
                logging.warning(f"[VAULT] Carte non trouvée dans le vault: user_id={user_id}, carte=({category}, {name})")
                return False
                
            except Exception as e:
                logging.error(f"[VAULT] Erreur lors du retrait du vault: {e}")
                return False
    
    def get_user_vault_cards(self, user_id: int) -> List[Tuple[str, str]]:
        """
        Récupère les cartes d'un utilisateur dans le vault.
        
        Args:
            user_id: ID de l'utilisateur
        
        Returns:
            List[Tuple[str, str]]: Liste des cartes (category, name)
        """
        vault_cache = self.storage.get_vault_cache()
        if not vault_cache:
            return []
        
        user_vault_cards = []
        for row in vault_cache[1:]:  # Skip header
            if len(row) < 3:
                continue
            
            cat, name = row[0], row[1]
            for cell in row[2:]:
                if not cell:
                    continue
                try:
                    uid, count = cell.split(":", 1)
                    uid = uid.strip()
                    if int(uid) == user_id:
                        user_vault_cards.extend([(cat, name)] * int(count))
                except (ValueError, IndexError) as e:
                    logging.warning(f"[SECURITY] Données corrompues dans get_user_vault_cards: {cell}, erreur: {e}")
                    continue
        
        return user_vault_cards
    
    def get_unique_vault_cards(self, user_id: int) -> List[Tuple[str, str]]:
        """Récupère les cartes uniques d'un utilisateur dans le vault."""
        vault_cards = self.get_user_vault_cards(user_id)
        return list(set(vault_cards))
    
    def clear_user_vault(self, user_id: int) -> bool:
        """
        Vide complètement le vault d'un utilisateur.
        
        Args:
            user_id: ID de l'utilisateur
        
        Returns:
            bool: True si succès
        """
        with self.storage._vault_lock:
            try:
                vault_cache = self.storage.get_vault_cache()
                if not vault_cache:
                    return True
                
                modified = False
                for i, row in enumerate(vault_cache):
                    if len(row) < 3:
                        continue
                    
                    original_len = len(row)
                    for j, cell in enumerate(row[2:], start=2):
                        if not cell:
                            continue
                        try:
                            uid, count = cell.split(":", 1)
                            uid = uid.strip()
                            if int(uid) == user_id:
                                row[j] = ""
                                modified = True
                        except (ValueError, IndexError) as e:
                            logging.warning(f"[SECURITY] Données corrompues dans clear_user_vault: {cell}, erreur: {e}")
                            continue
                    
                    if modified:
                        cleaned_row = merge_cells(row)
                        pad = max(original_len, len(cleaned_row)) - len(cleaned_row)
                        cleaned_row += [""] * pad
                        self.storage.sheet_vault.update(f"A{i+1}", [cleaned_row])
                
                if modified:
                    self.storage.refresh_vault_cache()
                    logging.info(f"[VAULT] Vault vidé pour l'utilisateur: user_id={user_id}")
                
                return True
                
            except Exception as e:
                logging.error(f"[VAULT] Erreur lors du vidage du vault: {e}")
                return False
