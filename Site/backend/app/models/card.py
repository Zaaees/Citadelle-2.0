"""
Modèles Pydantic pour les cartes.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class CardPair(BaseModel):
    """Simple paire catégorie/nom pour identifier une carte."""
    category: str = Field(..., description="Catégorie de la carte")
    name: str = Field(..., description="Nom de la carte (sans .png)")


class CardBase(BaseModel):
    """Modèle de base pour une carte."""
    category: str = Field(..., description="Catégorie de la carte")
    name: str = Field(..., description="Nom de la carte (sans .png)")
    file_id: Optional[str] = Field(None, description="ID du fichier Google Drive")
    is_full: bool = Field(False, description="Est-ce une carte Full?")


class Card(CardBase):
    """Modèle complet d'une carte avec métadonnées."""
    rarity_weight: float = Field(..., description="Poids de rareté de la catégorie")
    discoverer_id: Optional[int] = Field(None, description="ID du premier découvreur")
    discoverer_name: Optional[str] = Field(None, description="Nom du premier découvreur")
    discovery_date: Optional[datetime] = Field(None, description="Date de première découverte")


class CardInCollection(CardBase):
    """Carte dans la collection d'un utilisateur avec le nombre d'exemplaires."""
    count: int = Field(1, description="Nombre d'exemplaires possédés", ge=1)
    acquired_date: Optional[str] = Field(None, description="Date d'acquisition")


class UserCollection(BaseModel):
    """Collection de cartes d'un utilisateur."""
    user_id: int
    cards: List[CardInCollection] = Field(default_factory=list)
    total_cards: int = Field(0, description="Nombre total de cartes (avec doublons)")
    unique_cards: int = Field(0, description="Nombre de cartes uniques")
    completion_percentage: float = Field(0.0, description="Pourcentage de complétion", ge=0, le=100)

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": 123456789,
                "cards": [
                    {"category": "Élèves", "name": "Aria", "count": 3},
                    {"category": "Secrète", "name": "Mystère", "count": 1, "is_full": True}
                ],
                "total_cards": 4,
                "unique_cards": 2,
                "completion_percentage": 15.5
            }
        }


class CardDiscovery(BaseModel):
    """Informations sur la decouverte d'une carte."""
    category: str
    name: str
    discoverer_id: int
    discoverer_name: str
    timestamp: str = Field(..., description="Date de decouverte (format string)")
    discovery_index: int = Field(0, description="Numero de decouverte pour cette carte")


class RarityInfo(BaseModel):
    """Informations sur une catégorie de rareté."""
    category: str
    weight: float = Field(..., description="Poids de rareté (probabilité)")
    total_cards: int = Field(..., description="Nombre total de cartes dans cette catégorie")
    percentage: float = Field(..., description="Pourcentage de cette catégorie", ge=0, le=100)

class UpgradedCard(BaseModel):
    """Carte Full obtenue par upgrade (5 cartes normales → 1 Full)."""
    category: str
    name: str = Field(..., description="Nom de la carte Full (avec '(Full)')")
    file_id: Optional[str] = None
    original_name: str = Field(..., description="Nom de la carte normale d'origine")
    sacrificed_count: int = Field(5, description="Nombre de cartes sacrifiées")


class DrawResult(BaseModel):
    """Résultat d'un tirage avec les cartes obtenues et les upgrades éventuels."""
    drawn_cards: List[Card] = Field(..., description="Cartes obtenues par le tirage")
    upgraded_cards: List[UpgradedCard] = Field(
        default_factory=list,
        description="Cartes Full obtenues par conversion automatique (5 normales → 1 Full)"
    )

