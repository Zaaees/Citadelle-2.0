# 🎴 Citadelle Cards Web

Site web interactif pour le système de cartes du bot Discord Citadelle 2.0

## 🌟 Fonctionnalités

- **Authentification Discord OAuth2** - Connexion sécurisée avec votre compte Discord
- **Galerie Interactive** - Consultez toutes les cartes avec filtres par catégorie et rareté
- **Tirages Quotidiens** - Tirage journalier gratuit + tirage sacrificiel (5 cartes)
- **Système d'Échange** - Tableau d'échanges public et échanges directs entre utilisateurs
- **Profil Personnel** - Consultez votre collection, statistiques et découvertes
- **Temps Réel** - Notifications instantanées via WebSocket

## 🏗️ Architecture

### Stack Technologique

**Frontend**
- React 18 + TypeScript
- Vite (build tool)
- TailwindCSS (styling)
- Framer Motion (animations)
- Socket.io-client (WebSocket)

**Backend**
- Python 3.11+ / FastAPI
- Google Sheets API (base de données partagée avec le bot)
- Discord OAuth2
- WebSocket (notifications temps réel)
- JWT Authentication

## 🚀 Installation

### Prérequis

- Node.js 18+ et npm
- Python 3.11+
- Compte Discord Developer (pour OAuth2)
- Accès au Google Sheet du bot

### Backend Setup

```bash
cd backend

# Créer un environnement virtuel
python -m venv venv
source venv/bin/activate  # Sur Windows: venv\Scripts\activate

# Installer les dépendances
pip install -r requirements.txt

# Configurer les variables d'environnement
cp .env.example .env
# Éditer .env avec vos credentials

# Lancer le serveur
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend Setup

```bash
cd frontend

# Installer les dépendances
npm install

# Configurer l'environnement
cp .env.example .env.local
# Éditer .env.local avec l'URL de votre API

# Lancer le dev server
npm run dev
```

## 🔐 Configuration Discord OAuth2

1. Aller sur [Discord Developer Portal](https://discord.com/developers/applications)
2. Créer une nouvelle application ou utiliser celle existante
3. Dans "OAuth2" → "General":
   - Ajouter Redirect URL: `http://localhost:5173/auth/callback` (dev)
   - Ajouter Redirect URL: `https://votre-domaine.com/auth/callback` (prod)
4. Copier le Client ID et Client Secret
5. Ajouter ces valeurs dans `backend/.env`

## 📁 Structure du Projet

```
Site/
├── backend/              # API FastAPI
│   ├── app/
│   │   ├── api/         # Routes API
│   │   ├── core/        # Configuration
│   │   ├── services/    # Logique métier
│   │   ├── models/      # Modèles Pydantic
│   │   └── main.py      # Entry point
│   └── requirements.txt
│
├── frontend/            # Application React
│   ├── src/
│   │   ├── components/  # Composants React
│   │   ├── pages/       # Pages
│   │   ├── hooks/       # Custom hooks
│   │   └── services/    # API calls
│   └── package.json
│
└── docs/                # Documentation
```

## 🌐 Déploiement

### Backend (Render.com)

```yaml
Service Type: Web Service
Runtime: Python 3
Build Command: pip install -r requirements.txt
Start Command: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

### Frontend (Render.com)

```yaml
Service Type: Static Site
Build Command: npm run build
Publish Directory: dist
```

## 📖 Documentation

- [Architecture](docs/ARCHITECTURE.md) - Détails techniques de l'architecture
- [API Reference](docs/API.md) - Documentation complète de l'API
- [Deployment Guide](docs/DEPLOYMENT.md) - Guide de déploiement en production
- [User Guide](docs/USER_GUIDE.md) - Guide d'utilisation pour les utilisateurs finaux

## 🔗 Intégration avec le Bot Discord

Le site web et le bot Discord partagent la même base de données (Google Sheets), garantissant une synchronisation parfaite. Les utilisateurs se connectent avec leur compte Discord et accèdent à leurs données en temps réel.

## 🛠️ Développement

### Lancer en mode développement

```bash
# Terminal 1 - Backend
cd backend && uvicorn app.main:app --reload

# Terminal 2 - Frontend
cd frontend && npm run dev
```

### Tests

```bash
# Backend
cd backend && pytest

# Frontend
cd frontend && npm run test
```

## 📝 License

Ce projet est lié au bot Discord Citadelle 2.0 et suit la même license.

## 👥 Contributeurs

- Développement initial: Claude Code
- Bot Discord: Zaaees

---

🎴 Bon jeu et bons échanges ! ✨
