"""
API principale du site Citadelle Cards
FastAPI backend pour le système de cartes à collectionner
"""

from fastapi import FastAPI, Depends, HTTPException, status, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from typing import Optional, List
import logging
import io

from config import get_settings, RARITY_CONFIG, RARITY_ORDER
from models import (
    Token, TokenData, DiscordUser, ApiResponse,
    UserInventory, CardInInventory, DrawResult, DailyDrawStatus,
    UserVault, VaultCard, WeeklyTradeStatus, DiscoveryStats, UserStats
)
from auth import (
    get_oauth_url, exchange_code, get_discord_user,
    create_access_token, require_auth, get_current_user
)
from storage import get_storage_service
from drawing import get_drawing_service

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
settings = get_settings()

# Application FastAPI
app = FastAPI(
    title="Citadelle Cards API",
    description="API pour le système de cartes à collectionner Citadelle",
    version="1.0.0",
)

# CORS pour le frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============== Routes d'authentification ==============

@app.get("/api/auth/login")
async def login():
    """Redirige vers Discord pour l'authentification"""
    return RedirectResponse(url=get_oauth_url())


@app.get("/api/auth/callback")
async def auth_callback(code: str, response: Response):
    """Callback OAuth2 Discord"""
    # Échanger le code contre un token
    token_data = await exchange_code(code)
    if not token_data:
        raise HTTPException(status_code=400, detail="Échec de l'authentification Discord")

    # Récupérer les infos utilisateur
    discord_token = token_data.get("access_token")
    user = await get_discord_user(discord_token)
    if not user:
        raise HTTPException(status_code=400, detail="Impossible de récupérer les informations utilisateur")

    # Créer notre propre JWT
    access_token = create_access_token(user)

    # Rediriger vers le frontend avec le token
    redirect_url = f"{settings.frontend_url}/auth/callback?token={access_token}"
    return RedirectResponse(url=redirect_url)


@app.get("/api/auth/me")
async def get_me(current_user: TokenData = Depends(require_auth)):
    """Retourne les informations de l'utilisateur connecté"""
    return {
        "id": current_user.user_id,
        "username": current_user.username,
        "avatar": current_user.avatar,
        "avatar_url": f"https://cdn.discordapp.com/avatars/{current_user.user_id}/{current_user.avatar}.png"
        if current_user.avatar
        else f"https://cdn.discordapp.com/embed/avatars/0.png",
    }


@app.get("/api/auth/status")
async def auth_status(current_user: Optional[TokenData] = Depends(get_current_user)):
    """Vérifie le statut d'authentification"""
    return {"authenticated": current_user is not None}


# ============== Routes des cartes ==============

@app.get("/api/cards/inventory")
async def get_inventory(current_user: TokenData = Depends(require_auth)):
    """Récupère l'inventaire de l'utilisateur connecté"""
    storage = get_storage_service()
    cards = storage.get_user_cards(current_user.user_id)

    # Regrouper par catégorie et enrichir avec les infos de fichier
    inventory = []
    for category, name, count in cards:
        file_info = storage.find_card_file(category, name)
        inventory.append(CardInInventory(
            category=category,
            name=name,
            count=count,
            is_full="(Full)" in name,
            file_id=file_info['id'] if file_info else None,
        ))

    # Trier par rareté puis par nom
    def sort_key(card):
        try:
            rarity_idx = RARITY_ORDER.index(card.category)
        except ValueError:
            rarity_idx = 999
        return (rarity_idx, card.name)

    inventory.sort(key=sort_key)

    total = sum(c.count for c in inventory)
    unique = len(inventory)

    return UserInventory(
        user_id=current_user.user_id,
        cards=inventory,
        total_cards=total,
        unique_cards=unique,
    )


@app.get("/api/cards/image/{file_id}")
async def get_card_image(file_id: str):
    """Récupère l'image d'une carte"""
    storage = get_storage_service()
    image_bytes = storage.get_card_image(file_id)

    if not image_bytes:
        raise HTTPException(status_code=404, detail="Image non trouvée")

    return StreamingResponse(
        io.BytesIO(image_bytes),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},  # Cache 24h
    )


@app.get("/api/cards/catalog")
async def get_catalog():
    """Récupère le catalogue complet des cartes (découvertes uniquement)"""
    storage = get_storage_service()
    discovered = storage.get_discovered_cards()
    all_cards = storage.get_all_cards()

    catalog = {}
    for category in RARITY_ORDER:
        cards_in_cat = all_cards.get(category, [])
        catalog[category] = {
            "color": RARITY_CONFIG[category]["color"],
            "weight": RARITY_CONFIG[category]["weight"],
            "total": len(cards_in_cat),
            "discovered": sum(1 for c in cards_in_cat if (category, c['name']) in discovered),
            "cards": [
                {
                    "name": c['name'],
                    "file_id": c['id'],
                    "discovered": (category, c['name']) in discovered,
                }
                for c in cards_in_cat
            ],
        }

    return catalog


@app.get("/api/cards/stats")
async def get_stats(current_user: TokenData = Depends(require_auth)):
    """Récupère les statistiques de l'utilisateur"""
    storage = get_storage_service()
    cards = storage.get_user_cards(current_user.user_id)

    # Calculer les stats
    total_cards = sum(count for _, _, count in cards)
    unique_cards = len(cards)
    full_versions = sum(1 for _, name, _ in cards if "(Full)" in name)

    cards_by_category = {}
    for category, _, count in cards:
        cards_by_category[category] = cards_by_category.get(category, 0) + count

    # Découvertes de l'utilisateur
    # TODO: compter les découvertes de cet utilisateur

    return UserStats(
        total_cards=total_cards,
        unique_cards=unique_cards,
        full_versions=full_versions,
        cards_by_category=cards_by_category,
        discoveries_count=0,  # TODO
    )


# ============== Routes de tirage ==============

@app.get("/api/draw/status")
async def get_draw_status(current_user: TokenData = Depends(require_auth)):
    """Récupère le statut des tirages disponibles"""
    drawing = get_drawing_service()
    status = drawing.get_draw_status(current_user.user_id)
    return status


@app.post("/api/draw/daily")
async def perform_daily_draw(current_user: TokenData = Depends(require_auth)):
    """Effectue le tirage journalier"""
    drawing = get_drawing_service()
    success, cards, message = drawing.perform_daily_draw(
        current_user.user_id,
        current_user.username
    )

    if not success:
        raise HTTPException(status_code=400, detail=message)

    return {
        "success": True,
        "message": message,
        "cards": cards,
    }


@app.post("/api/draw/bonus")
async def perform_bonus_draw(current_user: TokenData = Depends(require_auth)):
    """Effectue un tirage bonus"""
    drawing = get_drawing_service()
    success, cards, message = drawing.perform_bonus_draw(
        current_user.user_id,
        current_user.username
    )

    if not success:
        raise HTTPException(status_code=400, detail=message)

    return {
        "success": True,
        "message": message,
        "cards": cards,
    }


@app.post("/api/draw/sacrificial")
async def perform_sacrificial_draw(
    selected_cards: List[dict],
    current_user: TokenData = Depends(require_auth)
):
    """Effectue un tirage sacrificiel"""
    # Convertir en liste de tuples
    cards_to_sacrifice = [(c["category"], c["name"]) for c in selected_cards]

    drawing = get_drawing_service()
    success, cards, message = drawing.perform_sacrificial_draw(
        current_user.user_id,
        current_user.username,
        cards_to_sacrifice
    )

    if not success:
        raise HTTPException(status_code=400, detail=message)

    return {
        "success": True,
        "message": message,
        "cards": cards,
    }


# ============== Routes du coffre ==============

@app.get("/api/vault")
async def get_vault(current_user: TokenData = Depends(require_auth)):
    """Récupère le contenu du coffre"""
    storage = get_storage_service()
    vault_cards = storage.get_user_vault(current_user.user_id)

    cards = [
        VaultCard(category=cat, name=name, count=count)
        for cat, name, count in vault_cards
    ]

    return UserVault(
        user_id=current_user.user_id,
        cards=cards,
        total_cards=sum(c.count for c in cards),
    )


@app.post("/api/vault/deposit")
async def deposit_to_vault(
    category: str,
    name: str,
    current_user: TokenData = Depends(require_auth)
):
    """Dépose une carte dans le coffre"""
    storage = get_storage_service()

    if not storage.add_to_vault(current_user.user_id, category, name):
        raise HTTPException(status_code=400, detail="Impossible de déposer cette carte")

    return {"success": True, "message": "Carte déposée dans le coffre"}


@app.post("/api/vault/withdraw")
async def withdraw_from_vault(
    category: str,
    name: str,
    current_user: TokenData = Depends(require_auth)
):
    """Retire une carte du coffre"""
    storage = get_storage_service()

    if not storage.remove_from_vault(current_user.user_id, category, name):
        raise HTTPException(status_code=400, detail="Impossible de retirer cette carte")

    return {"success": True, "message": "Carte retirée du coffre"}


# ============== Routes des échanges ==============

@app.get("/api/trade/status")
async def get_trade_status(current_user: TokenData = Depends(require_auth)):
    """Récupère le statut des échanges hebdomadaires"""
    storage = get_storage_service()
    trades_used = storage.get_weekly_trades_count(current_user.user_id)

    from datetime import datetime
    now = datetime.now()
    # Calculer le prochain lundi
    days_until_monday = (7 - now.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    next_monday = now.replace(hour=0, minute=0, second=0, microsecond=0)
    from datetime import timedelta
    next_monday += timedelta(days=days_until_monday)

    return WeeklyTradeStatus(
        trades_used=trades_used,
        trades_remaining=max(0, 3 - trades_used),
        week_reset_date=next_monday.isoformat(),
    )


# ============== Routes des découvertes ==============

@app.get("/api/discoveries")
async def get_discoveries():
    """Récupère les statistiques de découverte"""
    storage = get_storage_service()
    discovered = storage.get_discovered_cards()
    all_cards = storage.get_all_cards()

    by_category = {}
    total_cards = 0
    for category in RARITY_ORDER:
        cards_in_cat = all_cards.get(category, [])
        discovered_in_cat = sum(1 for c in cards_in_cat if (category, c['name']) in discovered)
        by_category[category] = {
            "discovered": discovered_in_cat,
            "total": len(cards_in_cat),
        }
        total_cards += len(cards_in_cat)

    return DiscoveryStats(
        total_discovered=len(discovered),
        total_cards=total_cards,
        by_category=by_category,
    )


@app.get("/api/discoveries/wall")
async def get_discovery_wall():
    """Récupère le mur des découvertes (toutes les cartes découvertes avec infos)"""
    storage = get_storage_service()
    all_cards = storage.get_all_cards()
    discovered = storage.get_discovered_cards()

    wall = []
    for category in RARITY_ORDER:
        cards_in_cat = all_cards.get(category, [])
        for card in cards_in_cat:
            if (category, card['name']) in discovered:
                info = storage.get_discovery_info(category, card['name'])
                wall.append({
                    "category": category,
                    "name": card['name'],
                    "file_id": card['id'],
                    "color": RARITY_CONFIG[category]["color"],
                    "discoverer_name": info['discoverer_name'] if info else "Inconnu",
                    "discovery_index": info['discovery_index'] if info else 0,
                    "timestamp": info['timestamp'] if info else None,
                })

    # Trier par index de découverte
    wall.sort(key=lambda x: x['discovery_index'])

    return wall


# ============== Routes de configuration ==============

@app.get("/api/config/rarities")
async def get_rarities():
    """Retourne la configuration des raretés"""
    return {
        category: {
            "weight": config["weight"],
            "color": config["color"],
        }
        for category, config in RARITY_CONFIG.items()
    }


@app.get("/ping")
async def ping():
    """Health check"""
    return {"status": "ok"}


@app.get("/health")
async def health():
    """Health check détaillé"""
    return {
        "status": "healthy",
        "service": "citadelle-cards-api",
        "version": "1.0.0",
    }


@app.get("/")
async def root():
    """Root endpoint for basic connectivity checks"""
    return {
        "message": "Citadelle Backend is running",
        "docs_url": "/docs"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.port)
