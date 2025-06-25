"""
Package pour le système de cartes à collectionner.
Ce package contient tous les modules nécessaires pour gérer les cartes,
les échanges, les tirages, et l'interface utilisateur.
"""

# Imports principaux pour faciliter l'utilisation du package
from .models import TradeExchangeState
from .config import *
from .utils import normalize_name, merge_cells

__version__ = "2.0.0"
__author__ = "Citadelle Bot"
