"""
Configuration du site web Citadelle Cards
Réutilise les mêmes variables d'environnement que le bot Discord
"""

import os
import json
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Discord OAuth2
    discord_client_id: str = ""
    discord_client_secret: str = ""
    discord_redirect_uri: str = "http://localhost:8000/api/auth/callback"

    # JWT pour les sessions
    secret_key: str = "change-this-in-production-use-a-real-secret-key"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 jours

    # Google Sheets (réutilise les mêmes que le bot)
    google_sheet_id_cartes: str = ""
    service_account_json: str = ""

    # Dossiers Google Drive pour les images de cartes
    folder_eleves_id: str = ""
    folder_autre_id: str = ""
    folder_professeurs_id: str = ""
    folder_architectes_id: str = ""
    folder_blackhole_id: str = ""
    folder_maitre_id: str = ""
    folder_historique_id: str = ""
    folder_fondateur_id: str = ""
    folder_secrete_id: str = ""

    # Dossiers Full versions
    folder_eleves_full_id: str = ""
    folder_autre_full_id: str = ""
    folder_professeurs_full_id: str = ""
    folder_architectes_full_id: str = ""
    folder_blackhole_full_id: str = ""
    folder_maitre_full_id: str = ""
    folder_historique_full_id: str = ""
    folder_fondateur_full_id: str = ""
    folder_secrete_full_id: str = ""

    # Frontend URL pour CORS
    frontend_url: str = "http://localhost:5173"

    # Server
    port: int = 8000

    class Config:
        env_file = "../../.env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


# Mapping des catégories vers les IDs de dossiers
def get_folder_ids(settings: Settings) -> dict:
    return {
        "Élèves": settings.folder_eleves_id,
        "Autre": settings.folder_autre_id,
        "Professeurs": settings.folder_professeurs_id,
        "Architectes": settings.folder_architectes_id,
        "Black Hole": settings.folder_blackhole_id,
        "Maître": settings.folder_maitre_id,
        "Historique": settings.folder_historique_id,
        "Fondateur": settings.folder_fondateur_id,
        "Secrète": settings.folder_secrete_id,
    }


def get_full_folder_ids(settings: Settings) -> dict:
    return {
        "Élèves": settings.folder_eleves_full_id,
        "Autre": settings.folder_autre_full_id,
        "Professeurs": settings.folder_professeurs_full_id,
        "Architectes": settings.folder_architectes_full_id,
        "Black Hole": settings.folder_blackhole_full_id,
        "Maître": settings.folder_maitre_full_id,
        "Historique": settings.folder_historique_full_id,
        "Fondateur": settings.folder_fondateur_full_id,
        "Secrète": settings.folder_secrete_full_id,
    }


# Configuration des raretés (identique au bot)
RARITY_CONFIG = {
    "Secrète": {"weight": 0.5, "color": "#9b59b6"},
    "Fondateur": {"weight": 1.0, "color": "#e74c3c"},
    "Historique": {"weight": 2.0, "color": "#f39c12"},
    "Maître": {"weight": 6.0, "color": "#3498db"},
    "Black Hole": {"weight": 6.0, "color": "#2c3e50"},
    "Architectes": {"weight": 7.0, "color": "#1abc9c"},
    "Professeurs": {"weight": 11.67, "color": "#27ae60"},
    "Autre": {"weight": 25.69, "color": "#95a5a6"},
    "Élèves": {"weight": 42.03, "color": "#f1c40f"},
}

# Ordre d'affichage des raretés (du plus rare au plus commun)
RARITY_ORDER = [
    "Secrète",
    "Fondateur",
    "Historique",
    "Maître",
    "Black Hole",
    "Architectes",
    "Professeurs",
    "Autre",
    "Élèves",
]
