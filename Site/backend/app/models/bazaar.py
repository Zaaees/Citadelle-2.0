"""
Modeles Pydantic pour le systeme Bazaar.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class TradeRequestStatus(str, Enum):
    """Statut d'une demande d'echange."""
    PENDING = "pending"      # En attente de reponse
    ACCEPTED = "accepted"    # Acceptee
    DECLINED = "declined"    # Refusee
    CANCELLED = "cancelled"  # Annulee par l'initiateur
    EXPIRED = "expired"      # Expiree (24h)


class CardInfo(BaseModel):
    """Information sur une carte."""
    category: str = Field(..., description="Categorie de la carte")
    name: str = Field(..., description="Nom de la carte")
    file_id: Optional[str] = Field(None, description="ID du fichier image Google Drive")


class CardAvailability(BaseModel):
    """Disponibilite d'une carte pour l'echange."""
    category: str
    name: str
    file_id: Optional[str] = None
    owners: List[dict] = Field(default_factory=list, description="Liste des proprietaires avec leur count")
    total_available: int = Field(0, description="Nombre total disponible a l'echange (doublons)")


class UserCardForTrade(BaseModel):
    """Carte d'un utilisateur disponible pour echange."""
    user_id: str = Field(..., description="ID Discord du proprietaire (string pour precision)")
    username: str = Field(..., description="Nom d'utilisateur")
    count: int = Field(..., description="Nombre d'exemplaires possedes")
    available_for_trade: int = Field(..., description="Nombre disponible a l'echange (count - 1 si option doublon)")


class TradeRequest(BaseModel):
    """Demande d'echange entre deux utilisateurs."""
    id: str = Field(..., description="ID unique de la demande")

    # Initiateur (celui qui propose l'echange)
    requester_id: str = Field(..., description="ID Discord de l'initiateur")
    requester_name: str = Field(..., description="Nom de l'initiateur")

    # Destinataire (celui qui recoit la demande)
    target_id: str = Field(..., description="ID Discord du destinataire")
    target_name: str = Field(..., description="Nom du destinataire")

    # Cartes echangees
    offered_card: CardInfo = Field(..., description="Carte offerte par l'initiateur")
    requested_card: CardInfo = Field(..., description="Carte demandee au destinataire")

    # Metadonnees
    status: TradeRequestStatus = Field(default=TradeRequestStatus.PENDING)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime = Field(..., description="Date d'expiration (24h apres creation)")
    resolved_at: Optional[datetime] = Field(None, description="Date de resolution")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "trade_123456",
                "requester_id": "249497144698863617",
                "requester_name": "Zaes",
                "target_id": "275734203268857868",
                "target_name": "OtherUser",
                "offered_card": {"category": "Eleves", "name": "Aria"},
                "requested_card": {"category": "Professeurs", "name": "L'infirmier"},
                "status": "pending",
                "created_at": "2025-12-21T10:00:00Z",
                "expires_at": "2025-12-22T10:00:00Z"
            }
        }


class TradeRequestCreate(BaseModel):
    """Schema pour creer une demande d'echange."""
    target_id: str = Field(..., description="ID Discord du destinataire")
    offered_category: str = Field(..., description="Categorie de la carte offerte")
    offered_name: str = Field(..., description="Nom de la carte offerte")
    requested_category: str = Field(..., description="Categorie de la carte demandee")
    requested_name: str = Field(..., description="Nom de la carte demandee")


class BazaarSearchParams(BaseModel):
    """Parametres de recherche dans le Bazaar."""
    query: Optional[str] = Field(None, description="Recherche textuelle")
    category: Optional[str] = Field(None, description="Filtrer par categorie")
    include_non_duplicates: bool = Field(False, description="Inclure les cartes non-doublons")
    page: int = Field(1, ge=1, description="Numero de page")
    per_page: int = Field(20, ge=1, le=100, description="Resultats par page")


class BazaarSearchResult(BaseModel):
    """Resultat de recherche dans le Bazaar."""
    cards: List[CardAvailability] = Field(default_factory=list)
    total: int = Field(0, description="Nombre total de resultats")
    page: int = Field(1)
    per_page: int = Field(20)
    total_pages: int = Field(1)


class UserTradeRequests(BaseModel):
    """Demandes d'echange d'un utilisateur."""
    received: List[TradeRequest] = Field(default_factory=list, description="Demandes recues")
    sent: List[TradeRequest] = Field(default_factory=list, description="Demandes envoyees")


class Notification(BaseModel):
    """Notification pour un utilisateur."""
    id: str
    user_id: str
    type: str = Field(..., description="Type: trade_request, trade_accepted, trade_declined, trade_expired")
    title: str
    message: str
    link: Optional[str] = None
    read: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    trade_request_id: Optional[str] = None
