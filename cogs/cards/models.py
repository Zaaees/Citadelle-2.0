"""
Modèles de données pour le système de cartes.
"""

import discord
from typing import Optional


class TradeExchangeState:
    """État d'un échange de cartes entre deux utilisateurs."""
    
    def __init__(self, cog, offerer: discord.User, target: discord.User, 
                 offer_cat: str, offer_name: str, return_cat: str, return_name: str):
        self.cog = cog
        self.offerer = offerer
        self.target = target
        self.offer_cat = offer_cat
        self.offer_name = offer_name
        self.return_cat = return_cat
        self.return_name = return_name
        self.confirmed_by_offer = False
        self.confirmed_by_target = False
        self.completed = False  # Pour éviter double validation


class CardInfo:
    """Informations sur une carte."""
    
    def __init__(self, category: str, name: str, file_id: str, is_full: bool = False):
        self.category = category
        self.name = name
        self.file_id = file_id
        self.is_full = is_full
    
    @property
    def display_name(self) -> str:
        """Nom d'affichage de la carte sans extension."""
        return self.name.removesuffix('.png')
    
    def __repr__(self):
        return f"CardInfo(category='{self.category}', name='{self.name}', is_full={self.is_full})"


class UserCardCollection:
    """Collection de cartes d'un utilisateur."""
    
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.cards: list[tuple[str, str]] = []  # (category, name)
    
    def add_card(self, category: str, name: str, count: int = 1):
        """Ajoute une ou plusieurs cartes à la collection."""
        for _ in range(count):
            self.cards.append((category, name))
    
    def remove_card(self, category: str, name: str) -> bool:
        """Retire une carte de la collection. Retourne True si succès."""
        try:
            self.cards.remove((category, name))
            return True
        except ValueError:
            return False
    
    def count_card(self, category: str, name: str) -> int:
        """Compte le nombre d'exemplaires d'une carte."""
        return self.cards.count((category, name))
    
    def get_unique_cards(self) -> list[tuple[str, str]]:
        """Retourne la liste des cartes uniques (sans doublons)."""
        return list(set(self.cards))
    
    def __len__(self):
        return len(self.cards)
