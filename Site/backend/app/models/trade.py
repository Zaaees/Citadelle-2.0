"""
Modèles Pydantic pour les échanges.
"""

from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class CardPair(BaseModel):
    """Paire catégorie/nom de carte."""
    category: str
    name: str


class TradeOfferCreate(BaseModel):
    """Création d'une offre sur le tableau d'échanges."""
    category: str = Field(..., description="Catégorie de la carte à échanger")
    name: str = Field(..., description="Nom de la carte à échanger")
    comment: Optional[str] = Field(None, max_length=200, description="Commentaire sur ce que vous cherchez")

    class Config:
        json_schema_extra = {
            "example": {
                "category": "Maître",
                "name": "Artemis",
                "comment": "Recherche cartes Élèves rares"
            }
        }


class TradeOffer(BaseModel):
    """Offre sur le tableau d'échanges."""
    id: int = Field(..., description="ID unique de l'offre")
    owner_id: int = Field(..., description="ID Discord du propriétaire")
    owner_name: Optional[str] = Field(None, description="Nom du propriétaire")
    category: str
    name: str
    comment: Optional[str] = None
    timestamp: datetime = Field(..., description="Date de dépôt de l'offre")

    class Config:
        json_schema_extra = {
            "example": {
                "id": 42,
                "owner_id": 123456789,
                "owner_name": "DragonSlayer",
                "category": "Maître",
                "name": "Artemis",
                "comment": "Recherche cartes Élèves rares",
                "timestamp": "2025-10-12T10:30:00Z"
            }
        }


class TradeProposal(BaseModel):
    """Proposition d'échange pour une offre du tableau."""
    board_offer_id: int = Field(..., description="ID de l'offre sur le tableau")
    offered_cards: List[CardPair] = Field(..., description="Cartes proposées en échange")

    class Config:
        json_schema_extra = {
            "example": {
                "board_offer_id": 42,
                "offered_cards": [
                    {"category": "Élèves", "name": "Aria"},
                    {"category": "Élèves", "name": "Luca"}
                ]
            }
        }


class DirectTradeRequest(BaseModel):
    """Demande d'échange direct entre deux utilisateurs."""
    target_user_id: int = Field(..., description="ID Discord de l'utilisateur cible")
    offered_cards: List[CardPair] = Field(..., description="Cartes que vous proposez")
    requested_cards: List[CardPair] = Field(..., description="Cartes que vous demandez")

    class Config:
        json_schema_extra = {
            "example": {
                "target_user_id": 987654321,
                "offered_cards": [
                    {"category": "Professeurs", "name": "Prof A"},
                    {"category": "Autre", "name": "Carte B"}
                ],
                "requested_cards": [
                    {"category": "Maître", "name": "Artemis"}
                ]
            }
        }


class TradeStatus(BaseModel):
    """Statut d'un échange en cours."""
    trade_id: str = Field(..., description="ID unique de l'échange")
    offerer_id: int
    offerer_confirmed: bool = Field(False, description="L'offreur a confirmé")
    target_id: int
    target_confirmed: bool = Field(False, description="La cible a confirmé")
    offered_cards: List[CardPair]
    requested_cards: List[CardPair]
    created_at: datetime
    status: str = Field(..., description="pending, confirmed, cancelled, completed")


class TradeHistory(BaseModel):
    """Historique d'un échange complété."""
    trade_id: str
    user1_id: int
    user1_name: str
    user2_id: int
    user2_name: str
    user1_gave: List[CardPair]
    user2_gave: List[CardPair]
    completed_at: datetime
    trade_type: str = Field(..., description="direct, board, vault")

    class Config:
        json_schema_extra = {
            "example": {
                "trade_id": "trade_abc123",
                "user1_id": 123456789,
                "user1_name": "DragonSlayer",
                "user2_id": 987654321,
                "user2_name": "MageSupreme",
                "user1_gave": [{"category": "Professeurs", "name": "Prof A"}],
                "user2_gave": [{"category": "Maître", "name": "Artemis"}],
                "completed_at": "2025-10-12T14:30:00Z",
                "trade_type": "direct"
            }
        }


class VaultTradeRequest(BaseModel):
    """Demande d'échange de vault complet."""
    target_user_id: int = Field(..., description="ID Discord de l'utilisateur avec qui échanger tout le vault")

    class Config:
        json_schema_extra = {
            "example": {
                "target_user_id": 987654321
            }
        }
