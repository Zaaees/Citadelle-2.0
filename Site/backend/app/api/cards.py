"""
Routes pour la gestion des cartes.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from typing import List, Optional
import logging
import asyncio

from ..core.dependencies import get_current_user, get_optional_user
from ..models.card import Card, RarityInfo, CardDiscovery
from ..services.cards_service import card_system

router = APIRouter()
logger = logging.getLogger(__name__)

# Cache LRU pour les images (max 500 images, ~250MB si 500KB par image)
from collections import OrderedDict

class LRUImageCache:
    """Cache LRU pour les images avec limite de taille."""

    def __init__(self, max_size: int = 500):
        self.cache = OrderedDict()
        self.max_size = max_size

    def get(self, key: str) -> bytes | None:
        if key in self.cache:
            # Déplacer en fin (most recently used)
            self.cache.move_to_end(key)
            return self.cache[key]
        return None

    def set(self, key: str, value: bytes):
        if key in self.cache:
            self.cache.move_to_end(key)
        else:
            if len(self.cache) >= self.max_size:
                # Supprimer le plus ancien (least recently used)
                self.cache.popitem(last=False)
            self.cache[key] = value

    def __contains__(self, key: str) -> bool:
        return key in self.cache

    def __len__(self) -> int:
        return len(self.cache)

_image_cache = LRUImageCache(max_size=500)


@router.get("/", response_model=List[Card])
async def get_all_cards(
    category: Optional[str] = Query(None, description="Filtrer par catégorie"),
    current_user: Optional[dict] = Depends(get_optional_user)
):
    """
    Récupère toutes les cartes disponibles dans le jeu.

    Args:
        category: Filtre optionnel par catégorie

    Returns:
        Liste de toutes les cartes
    """
    logger.info(f"Récupération des cartes (catégorie: {category})")

    try:
        all_cards = card_system.get_all_cards(category=category)

        # Convertir en objets Card
        cards = [
            Card(
                category=card["category"],
                name=card["name"],
                file_id=card.get("file_id"),
                is_full=card["is_full"],
                rarity_weight=card["rarity_weight"]
            )
            for card in all_cards
        ]

        return cards

    except Exception as e:
        logger.error(f"Erreur lors de la récupération des cartes: {e}")
        raise HTTPException(status_code=500, detail="Erreur lors de la récupération des cartes")


@router.get("/categories", response_model=List[RarityInfo])
async def get_categories():
    """
    Récupère la liste des catégories de cartes avec leurs probabilités.

    Returns:
        Liste des catégories avec poids de rareté et nombre de cartes
    """
    logger.info("Récupération des catégories")

    try:
        categories_data = card_system.get_categories_info()

        categories = [
            RarityInfo(
                category=cat["category"],
                weight=cat["weight"],
                total_cards=cat["total_cards"],
                percentage=cat["percentage"]
            )
            for cat in categories_data
        ]

        return categories

    except Exception as e:
        logger.error(f"Erreur lors de la récupération des catégories: {e}")
        raise HTTPException(status_code=500, detail="Erreur lors de la récupération des catégories")


@router.get("/discoveries", response_model=List[CardDiscovery])
async def get_recent_discoveries(
    limit: int = Query(20, ge=1, le=100, description="Nombre de découvertes à retourner")
):
    """
    Récupère les découvertes récentes (premières obtentions de cartes).

    Args:
        limit: Nombre de découvertes à retourner

    Returns:
        Liste des découvertes récentes
    """
    # TODO: Implémenter la récupération depuis la feuille "Découvertes"
    logger.info(f"Récupération des {limit} dernières découvertes")
    return []


@router.get("/image/{file_id}")
async def get_card_image(file_id: str):
    """
    Récupère l'image d'une carte depuis Google Drive avec cache LRU.

    Args:
        file_id: ID du fichier Google Drive

    Returns:
        Image au format PNG
    """
    try:
        # Vérifier le cache LRU
        cached_image = _image_cache.get(file_id)
        if cached_image is not None:
            logger.debug(f"📦 Image {file_id} depuis le cache ({len(_image_cache)} en cache)")
            return Response(
                content=cached_image,
                media_type="image/png",
                headers={
                    "Cache-Control": "public, max-age=604800",  # 7 jours
                    "Access-Control-Allow-Origin": "*"
                }
            )

        logger.info(f"🖼️  Téléchargement de l'image {file_id}")

        import httpx

        # Essayer plusieurs URLs en fallback (URL la plus rapide en premier)
        urls = [
            f"https://lh3.googleusercontent.com/d/{file_id}",
            f"https://drive.google.com/uc?export=view&id={file_id}",
            f"https://drive.google.com/uc?export=download&id={file_id}",
        ]

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            for i, url in enumerate(urls):
                try:
                    response = await client.get(url)

                    if response.status_code == 200 and len(response.content) > 500:
                        file_bytes = response.content

                        # Mettre en cache LRU (gère automatiquement la limite)
                        _image_cache.set(file_id, file_bytes)

                        logger.info(f"✅ Image {file_id} téléchargée avec URL {i+1} ({len(file_bytes)} bytes, cache: {len(_image_cache)})")

                        return Response(
                            content=file_bytes,
                            media_type="image/png",
                            headers={
                                "Cache-Control": "public, max-age=604800",  # 7 jours
                                "Access-Control-Allow-Origin": "*"
                            }
                        )
                except Exception as url_error:
                    logger.warning(f"URL {i+1} échouée pour {file_id}: {url_error}")
                    continue

            raise Exception(f"Toutes les URLs ont échoué pour {file_id}")

    except Exception as e:
        logger.error(f"❌ Erreur lors du téléchargement de l'image {file_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors du téléchargement de l'image: {str(e)}"
        )



@router.get("/inventory", response_model=dict)
async def get_user_inventory(
    current_user: dict = Depends(get_current_user)
):
    """
    Récupère l'inventaire de cartes de l'utilisateur connecté.
    """
    logger.info(f"Récupération inventaire pour {current_user.get('username')} ({current_user.get('id')})")
    try:
        inventory = await card_system.get_user_collection(int(current_user["id"]))
        return inventory
    except Exception as e:
        logger.error(f"Erreur lors de la récupération de l'inventaire: {e}")
        raise HTTPException(status_code=500, detail="Erreur lors de la récupération de l'inventaire")


@router.get("/{category}/{name}", response_model=Card)
async def get_card_details(
    category: str,
    name: str,
    current_user: Optional[dict] = Depends(get_optional_user)
):
    """
    Récupère les détails d'une carte spécifique.
    
    Args:
        category: Catégorie de la carte
        name: Nom de la carte
        
    Returns:
        Détails complets de la carte avec découvreur, etc.
    """
    # TODO: Implémenter la récupération depuis Google Sheets
    logger.info(f"Récupération de la carte: {category}/{name}")
    raise HTTPException(status_code=404, detail="Carte non trouvée")

