"""
Modèles Pydantic pour l'API
"""

from pydantic import BaseModel
from typing import Optional, List, Tuple
from datetime import datetime


# ============== Utilisateur ==============

class DiscordUser(BaseModel):
    """Utilisateur Discord authentifié"""
    id: str
    username: str
    discriminator: str
    avatar: Optional[str] = None
    global_name: Optional[str] = None

    @property
    def display_name(self) -> str:
        return self.global_name or self.username

    @property
    def avatar_url(self) -> str:
        if self.avatar:
            return f"https://cdn.discordapp.com/avatars/{self.id}/{self.avatar}.png"
        return f"https://cdn.discordapp.com/embed/avatars/{int(self.discriminator or '0') % 5}.png"


class Token(BaseModel):
    """Token JWT"""
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Données contenues dans le token"""
    user_id: str
    username: str
    avatar: Optional[str] = None


# ============== Cartes ==============

class CardInfo(BaseModel):
    """Information sur une carte"""
    category: str
    name: str
    file_id: str
    is_full: bool = False

    @property
    def display_name(self) -> str:
        return self.name.replace(".png", "").replace(" (Full)", "")


class CardInInventory(BaseModel):
    """Carte dans l'inventaire d'un utilisateur"""
    category: str
    name: str
    count: int
    is_full: bool = False
    file_id: Optional[str] = None

    @property
    def display_name(self) -> str:
        return self.name.replace(".png", "").replace(" (Full)", "")


class UserInventory(BaseModel):
    """Inventaire complet d'un utilisateur"""
    user_id: str
    cards: List[CardInInventory]
    total_cards: int
    unique_cards: int


class DrawResult(BaseModel):
    """Résultat d'un tirage"""
    cards: List[CardInfo]
    is_new_discovery: List[bool]
    can_draw_again: bool = False
    message: Optional[str] = None


class DailyDrawStatus(BaseModel):
    """Statut du tirage journalier"""
    can_draw: bool
    last_draw_date: Optional[str] = None
    bonus_available: int = 0
    sacrificial_available: bool = False


# ============== Coffre (Vault) ==============

class VaultCard(BaseModel):
    """Carte dans le coffre"""
    category: str
    name: str
    count: int


class UserVault(BaseModel):
    """Coffre d'un utilisateur"""
    user_id: str
    cards: List[VaultCard]
    total_cards: int


# ============== Échanges ==============

class BoardOffer(BaseModel):
    """Offre sur le tableau d'échange"""
    id: str
    owner_id: str
    owner_name: str
    category: str
    name: str
    timestamp: datetime
    comment: Optional[str] = None


class TradeRequest(BaseModel):
    """Demande d'échange direct"""
    target_user_id: str
    offer_cards: List[Tuple[str, str]]  # [(category, name), ...]
    request_cards: List[Tuple[str, str]]


class WeeklyTradeStatus(BaseModel):
    """Statut des échanges hebdomadaires"""
    trades_used: int
    trades_remaining: int
    week_reset_date: str


# ============== Découvertes ==============

class DiscoveryInfo(BaseModel):
    """Information sur une découverte"""
    category: str
    name: str
    discoverer_id: str
    discoverer_name: str
    timestamp: str
    discovery_index: int


class DiscoveryStats(BaseModel):
    """Statistiques de découverte globales"""
    total_discovered: int
    total_cards: int
    by_category: dict


# ============== Statistiques ==============

class UserStats(BaseModel):
    """Statistiques d'un utilisateur"""
    total_cards: int
    unique_cards: int
    full_versions: int
    cards_by_category: dict
    discoveries_count: int
    rank: Optional[int] = None


class GlobalStats(BaseModel):
    """Statistiques globales"""
    total_cards_in_circulation: int
    total_unique_cards: int
    total_discoveries: int
    cards_by_category: dict
    top_collectors: List[dict]


# ============== Réponses API ==============

class ApiResponse(BaseModel):
    """Réponse générique de l'API"""
    success: bool
    message: Optional[str] = None
    data: Optional[dict] = None


class ErrorResponse(BaseModel):
    """Réponse d'erreur"""
    detail: str
    error_code: Optional[str] = None
