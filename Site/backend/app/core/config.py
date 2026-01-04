"""
Configuration centrale de l'application.
Charge les variables d'environnement et définit les settings.
"""

from pydantic_settings import BaseSettings
from typing import List
import json


class Settings(BaseSettings):
    """Configuration de l'application."""

    # Server
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    DEBUG: bool = True
    ENVIRONMENT: str = "development"

    # Frontend (CORS)
    FRONTEND_URL: str = "http://localhost:5173"

    @property
    def CORS_ORIGINS(self) -> List[str]:
        """Liste des origines autorisées pour CORS."""
        origins = [
            "http://localhost:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:5174"
        ]

        if self.FRONTEND_URL:
            # Nettoyer l'URL (enlever le trailing slash qui peut casser CORS)
            clean_url = self.FRONTEND_URL.rstrip('/')
            origins.append(clean_url)
            
            # Ajouter la version avec/sans www si nécessaire (optionnel mais robuste)
            if "://" in clean_url:
                protocol, domain = clean_url.split("://", 1)
                # origins.append(f"{protocol}://www.{domain}") 

        return origins

    # Discord OAuth2
    DISCORD_CLIENT_ID: str
    DISCORD_CLIENT_SECRET: str
    DISCORD_REDIRECT_URI: str

    DISCORD_API_ENDPOINT: str = "https://discord.com/api/v10"
    DISCORD_OAUTH_AUTHORIZE: str = "https://discord.com/api/oauth2/authorize"
    DISCORD_OAUTH_TOKEN: str = "https://discord.com/api/oauth2/token"
    DISCORD_OAUTH_REVOKE: str = "https://discord.com/api/oauth2/token/revoke"

    # JWT
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Google Sheets
    SERVICE_ACCOUNT_JSON: str
    GOOGLE_SHEET_ID: str

    # Google Drive Folders (cartes par catégorie)
    FOLDER_ELEVES_ID: str
    FOLDER_PROFESSEURS_ID: str
    FOLDER_ARCHITECTES_ID: str
    FOLDER_MAITRE_ID: str
    FOLDER_FONDATEUR_ID: str
    FOLDER_PERSONNAGE_HISTORIQUE_ID: str
    FOLDER_SECRETE_ID: str
    FOLDER_BLACKHOLE_ID: str
    FOLDER_AUTRE_ID: str

    # Google Drive Folders (cartes Full par catégorie) - optionnels
    FOLDER_ELEVES_FULL_ID: str = ""
    FOLDER_PROFESSEURS_FULL_ID: str = ""
    FOLDER_ARCHITECTES_FULL_ID: str = ""
    FOLDER_MAITRE_FULL_ID: str = ""
    FOLDER_FONDATEUR_FULL_ID: str = ""
    FOLDER_HISTORIQUE_FULL_ID: str = ""
    FOLDER_SECRETE_FULL_ID: str = ""
    FOLDER_BLACKHOLE_FULL_ID: str = ""
    FOLDER_AUTRE_FULL_ID: str = ""

    @property
    def SERVICE_ACCOUNT_INFO(self) -> dict:
        """Parse le JSON du service account."""
        if not self.SERVICE_ACCOUNT_JSON:
            return {}

        try:
            # Nettoyage: retirer les quotes simples ou doubles qui pourraient entourer le JSON
            cleaned_json = self.SERVICE_ACCOUNT_JSON.strip()
            if cleaned_json.startswith("'") and cleaned_json.endswith("'"):
                cleaned_json = cleaned_json[1:-1]
            elif cleaned_json.startswith('"') and cleaned_json.endswith('"'):
                cleaned_json = cleaned_json[1:-1]
            
            account_info = json.loads(cleaned_json)

            # Fix: Convertir les \n échappés en vraies nouvelles lignes dans la clé privée
            if 'private_key' in account_info:
                account_info['private_key'] = account_info['private_key'].replace('\\n', '\n')

            return account_info
        except json.JSONDecodeError as e:
            # En cas d'erreur, retourner un dict vide mais logger l'erreur (dans une vraie app)
            print(f"❌ Erreur de parsing SERVICE_ACCOUNT_JSON: {e}")
            return {}
        except Exception as e:
            print(f"❌ Erreur inattendue SERVICE_ACCOUNT_JSON: {e}")
            return {}

    # Logging
    LOG_LEVEL: str = "INFO"

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60

    # WebSocket
    WEBSOCKET_PING_INTERVAL: int = 25
    WEBSOCKET_PING_TIMEOUT: int = 60

    # Application Info
    APP_NAME: str = "Citadelle Cards API"
    APP_VERSION: str = "1.0.0"
    APP_DESCRIPTION: str = "API pour le système de cartes Citadelle"

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


# Instance globale des settings
settings = Settings()
