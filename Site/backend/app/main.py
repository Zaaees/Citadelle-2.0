"""
Point d'entrée principal de l'API FastAPI.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging

from .core.config import settings
from .api import auth, cards, draw, trade, user, vault

# Configuration du logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='[%(asctime)s] %(levelname)s - %(name)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Création de l'application FastAPI
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=settings.APP_DESCRIPTION,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

# Configuration CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inclusion des routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(cards.router, prefix="/api/cards", tags=["Cards"])
app.include_router(draw.router, prefix="/api/draw", tags=["Drawing"])
app.include_router(trade.router, prefix="/api/trade", tags=["Trading"])
app.include_router(user.router, prefix="/api/user", tags=["User"])
app.include_router(vault.router, prefix="/api/vault", tags=["Vault"])


@app.on_event("startup")
async def startup_event():
    """Actions à effectuer au démarrage de l'application."""
    logger.info(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} démarré")
    logger.info(f"📝 Environment: {settings.ENVIRONMENT}")
    logger.info(f"🔗 Frontend URL: {settings.FRONTEND_URL}")


@app.on_event("shutdown")
async def shutdown_event():
    """Actions à effectuer à l'arrêt de l'application."""
    logger.info(f"🛑 {settings.APP_NAME} arrêté")


@app.get("/")
async def root():
    """Endpoint racine pour vérifier que l'API fonctionne."""
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "online",
        "docs": "/docs" if settings.DEBUG else "disabled"
    }


@app.get("/health")
async def health_check():
    """Health check pour les services de monitoring."""
    return {"status": "healthy", "environment": settings.ENVIRONMENT}


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Gestionnaire d'exceptions global."""
    logger.error(f"Erreur non gérée: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Une erreur interne est survenue"}
    )
