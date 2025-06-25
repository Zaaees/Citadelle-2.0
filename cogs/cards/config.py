"""
Configuration et constantes pour le système de cartes.
"""

# Configuration des rôles
CARD_COLLECTOR_ROLE_ID = 1386125369295245388

# Configuration du forum
CARD_FORUM_CHANNEL_ID = 1386299170406531123

# Poids de rareté pour les tirages
RARITY_WEIGHTS = {
    "Secrète": 0.005,
    "Fondateur": 0.01,
    "Historique": 0.02,
    "Maître": 0.06,
    "Black Hole": 0.06,
    "Architectes": 0.07,
    "Professeurs": 0.1167,
    "Autre": 0.2569,
    "Élèves": 0.4203
}

# Catégories de cartes dans l'ordre
ALL_CATEGORIES = [
    "Secrète", "Fondateur", "Historique", "Maître", "Black Hole",
    "Architectes", "Professeurs", "Autre", "Élèves"
]

# Configuration du cache (en secondes)
CACHE_VALIDITY_DURATION = 5

# Configuration des échanges
WEEKLY_EXCHANGE_LIMIT = 3
DAILY_SACRIFICIAL_CARDS_COUNT = 5
