"""
Fonctions utilitaires pour le système de cartes.
"""

import unicodedata
import logging
from typing import Dict, Any, List


def normalize_name(name: str) -> str:
    """Supprime les accents et met en minuscules pour comparaison insensible."""
    return ''.join(
        c for c in unicodedata.normalize('NFD', name)
        if unicodedata.category(c) != 'Mn'
    ).lower()


def merge_cells(row: List[str]) -> List[str]:
    """Fusionne les colonnes d'un même utilisateur en nettoyant les espaces."""
    merged = {}
    for cell in row:
        if not cell or ":" not in cell:
            continue
        try:
            uid, count = cell.split(":", 1)
            uid = uid.strip()
            count = int(count.strip())
            merged[uid] = merged.get(uid, 0) + count
        except (ValueError, IndexError) as e:
            logging.warning(f"[SECURITY] Données corrompues dans merge_cells: {cell}, erreur: {e}")
            continue
    
    return [f"{uid}:{count}" for uid, count in merged.items() if count > 0]


def parse_card_input(input_text: str) -> tuple[str, bool]:
    """
    Parse l'entrée utilisateur pour identifier une carte.
    
    Args:
        input_text: Texte saisi par l'utilisateur (nom de carte ou ID)
    
    Returns:
        tuple: (nom_normalisé, is_card_id)
    """
    input_text = input_text.strip()
    
    # Vérifier si c'est un ID de carte (format C123)
    if input_text.upper().startswith('C') and input_text[1:].isdigit():
        return input_text.upper(), True
    
    # Sinon, traiter comme un nom de carte
    if not input_text.lower().endswith(".png"):
        input_text += ".png"
    
    return normalize_name(input_text.removesuffix(".png")), False


def format_card_display(category: str, name: str, card_id: str = None) -> str:
    """
    Formate l'affichage d'une carte avec son ID si disponible.
    
    Args:
        category: Catégorie de la carte
        name: Nom de la carte
        card_id: ID de la carte (optionnel)
    
    Returns:
        str: Texte formaté pour l'affichage
    """
    display_name = name.removesuffix('.png')
    if card_id:
        return f"{display_name} ({card_id})"
    return display_name


def validate_card_data(category: str, name: str, user_id: int) -> bool:
    """
    Valide les données d'une carte.
    
    Args:
        category: Catégorie de la carte
        name: Nom de la carte
        user_id: ID de l'utilisateur
    
    Returns:
        bool: True si les données sont valides
    """
    if not category or not name or user_id <= 0:
        logging.error(f"[SECURITY] Paramètres invalides: user_id={user_id}, category='{category}', name='{name}'")
        return False
    
    return True


def is_full_card(name: str) -> bool:
    """Vérifie si une carte est une carte Full."""
    return "(Full)" in name


def get_card_display_name(name: str) -> str:
    """Retourne le nom d'affichage d'une carte sans extension."""
    return name.removesuffix('.png')
