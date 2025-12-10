"""
Modèles Pydantic pour les utilisateurs.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class UserBase(BaseModel):
    """Modèle de base pour un utilisateur Discord."""
    user_id: int = Field(..., description="Discord User ID")
    username: str = Field(..., description="Discord username")
    discriminator: str = Field(default="0", description="Discord discriminator")
    global_name: Optional[str] = Field(None, description="Discord display name")
    avatar: Optional[str] = Field(None, description="Avatar hash Discord")


class User(UserBase):
    """Modèle complet d'un utilisateur avec ses statistiques."""
    total_cards: int = Field(0, description="Nombre total de cartes possédées")
    unique_cards: int = Field(0, description="Nombre de cartes uniques")
    discoveries: int = Field(0, description="Nombre de découvertes (première obtention)")
    total_trades: int = Field(0, description="Nombre d'échanges effectués")
    last_daily_draw: Optional[datetime] = Field(None, description="Date du dernier tirage journalier")
    last_sacrificial_draw: Optional[datetime] = Field(None, description="Date du dernier tirage sacrificiel")

    @property
    def avatar_url(self) -> Optional[str]:
        """URL complète de l'avatar Discord."""
        if self.avatar:
            return f"https://cdn.discordapp.com/avatars/{self.user_id}/{self.avatar}.png"
        # Avatar par défaut Discord
        default_avatar_index = (self.user_id >> 22) % 6
        return f"https://cdn.discordapp.com/embed/avatars/{default_avatar_index}.png"

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": 123456789,
                "username": "DragonSlayer",
                "discriminator": "0",
                "global_name": "Dragon Slayer",
                "avatar": "abc123def456",
                "total_cards": 47,
                "unique_cards": 35,
                "discoveries": 2,
                "total_trades": 8,
                "last_daily_draw": "2025-10-12T10:30:00Z",
                "last_sacrificial_draw": "2025-10-11T15:45:00Z"
            }
        }


class UserStats(BaseModel):
    """Statistiques détaillées d'un utilisateur."""
    user: User
    cards_by_rarity: dict[str, int] = Field(
        default_factory=dict,
        description="Nombre de cartes par catégorie"
    )
    completion_by_rarity: dict[str, float] = Field(
        default_factory=dict,
        description="Pourcentage de complétion par catégorie"
    )
    weekly_trades_remaining: int = Field(3, description="Échanges restants cette semaine", ge=0, le=3)
    can_daily_draw: bool = Field(True, description="Peut effectuer le tirage journalier?")
    can_sacrificial_draw: bool = Field(True, description="Peut effectuer le tirage sacrificiel?")


class AuthResponse(BaseModel):
    """Réponse d'authentification."""
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Type de token")
    user: UserBase
    expires_in: int = Field(..., description="Durée de validité du token en secondes")

    class Config:
        json_schema_extra = {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIs...",
                "token_type": "bearer",
                "user": {
                    "user_id": 123456789,
                    "username": "DragonSlayer",
                    "discriminator": "0",
                    "global_name": "Dragon Slayer",
                    "avatar": "abc123def456"
                },
                "expires_in": 3600
            }
        }
