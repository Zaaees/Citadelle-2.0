# 🚀 Guide de Démarrage Rapide - Citadelle Cards Web

Ce guide vous aidera à démarrer le développement du site web de cartes Citadelle.

## 📦 Ce qui a été créé

### Structure Complète du Projet

```
Site/
├── backend/              ✅ Backend FastAPI complet
│   ├── app/
│   │   ├── api/         ✅ Routes API (auth, cards, draw, trade, user)
│   │   ├── core/        ✅ Configuration, sécurité, dépendances
│   │   ├── models/      ✅ Modèles Pydantic (card, user, trade)
│   │   ├── services/    ⏳ À compléter (réutilisation du code du bot)
│   │   └── main.py      ✅ Point d'entrée FastAPI
│   ├── requirements.txt ✅ Dépendances Python
│   └── .env.example     ✅ Template de configuration
│
├── frontend/            ✅ Configuration React + TypeScript + Vite
│   ├── src/            ⏳ À développer
│   ├── package.json    ✅ Dépendances Node
│   ├── tsconfig.json   ✅ Configuration TypeScript
│   ├── vite.config.ts  ✅ Configuration Vite
│   ├── tailwind.config ✅ Thème fantastique personnalisé
│   └── index.html      ✅ Point d'entrée HTML
│
├── docs/               ⏳ Documentation à compléter
├── README.md           ✅ Documentation principale
└── GETTING_STARTED.md  ✅ Ce guide
```

### ✅ Fonctionnalités Backend Créées

1. **Authentification Discord OAuth2** (`backend/app/api/auth.py`)
   - `/api/auth/discord` - URL d'autorisation Discord
   - `/api/auth/discord/callback` - Callback OAuth2
   - `/api/auth/me` - Informations utilisateur
   - `/api/auth/logout` - Déconnexion
   - JWT tokens avec expiration

2. **Routes API Cartes** (`backend/app/api/cards.py`)
   - GET `/api/cards` - Liste des cartes (avec filtre par catégorie)
   - GET `/api/cards/categories` - Catégories et raretés
   - GET `/api/cards/{category}/{name}` - Détails d'une carte
   - GET `/api/cards/discoveries` - Découvertes récentes

3. **Routes API Tirages** (`backend/app/api/draw.py`)
   - GET `/api/draw/daily/status` - Statut tirage journalier
   - POST `/api/draw/daily` - Effectuer tirage journalier
   - GET `/api/draw/sacrificial/status` - Statut tirage sacrificiel
   - GET `/api/draw/sacrificial/preview` - Aperçu des 5 cartes
   - POST `/api/draw/sacrificial` - Effectuer tirage sacrificiel

4. **Routes API Échanges** (`backend/app/api/trade.py`)
   - GET `/api/trade/board` - Tableau d'échanges
   - POST `/api/trade/board` - Déposer une offre
   - DELETE `/api/trade/board/{id}` - Retirer une offre
   - POST `/api/trade/board/{id}/accept` - Accepter une offre
   - POST `/api/trade/direct` - Échange direct
   - GET `/api/trade/history` - Historique
   - GET `/api/trade/weekly-limit` - Limite hebdomadaire
   - POST `/api/trade/vault/exchange` - Échange de vault

5. **Routes API Utilisateur** (`backend/app/api/user.py`)
   - GET `/api/user/collection` - Collection complète
   - GET `/api/user/stats` - Statistiques détaillées
   - GET `/api/user/discoveries` - Découvertes personnelles
   - GET `/api/user/vault` - Contenu du vault

### ✅ Configuration Frontend Créée

1. **React + TypeScript + Vite** - Build tool moderne et rapide
2. **TailwindCSS** - Thème fantastique personnalisé (violet, rose, or)
3. **Framer Motion** - Animations fluides
4. **React Query** - Gestion du cache et des requêtes API
5. **Zustand** - State management
6. **Socket.io** - WebSocket pour temps réel
7. **Axios** - Client HTTP

## 🛠️ Étapes Suivantes

### Étape 1: Configuration de l'Environnement

#### Backend

```bash
cd backend

# Créer un environnement virtuel
python -m venv venv
source venv/bin/activate  # Sur Windows: venv\Scripts\activate

# Installer les dépendances
pip install -r requirements.txt

# Configurer les variables d'environnement
cp .env.example .env
# Éditer .env avec vos credentials Discord et Google Sheets
```

**Variables d'environnement importantes:**
- `DISCORD_CLIENT_ID` et `DISCORD_CLIENT_SECRET` - Depuis Discord Developer Portal
- `SERVICE_ACCOUNT_JSON` - Credentials Google Sheets (même que le bot)
- `GOOGLE_SHEET_ID` - ID de la feuille Google Sheets (même que le bot)
- `JWT_SECRET_KEY` - Générer une clé secrète forte

#### Frontend

```bash
cd frontend

# Installer les dépendances
npm install

# Configurer les variables d'environnement
cp .env.example .env.local
# Éditer .env.local avec l'URL de votre API
```

### Étape 2: Implémenter les Services Backend

Les routes API sont créées mais appellent des TODO. Vous devez maintenant:

#### A. Réutiliser le code du bot

Créez des fichiers dans `backend/app/services/` qui importent et utilisent le code existant:

**Exemple pour `backend/app/services/storage_service.py`:**

```python
import sys
import os

# Ajouter le chemin vers le code du bot
sys.path.append(os.path.join(os.path.dirname(__file__), '../../../../cogs/cards'))

from storage import CardsStorage
from drawing import DrawingManager
from trading import TradingManager
from vault import VaultManager
import gspread
from oauth2client.service_account import ServiceAccountCredentials

from ..core.config import settings

class CardSystemService:
    """Service singleton pour accéder au système de cartes."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        # Initialiser la connexion Google Sheets
        scope = ['https://spreadsheets.google.com/feeds',
                 'https://www.googleapis.com/auth/drive']

        creds = ServiceAccountCredentials.from_json_keyfile_dict(
            settings.SERVICE_ACCOUNT_INFO,
            scope
        )

        self.gspread_client = gspread.authorize(creds)

        # Initialiser le storage
        self.storage = CardsStorage(
            self.gspread_client,
            settings.GOOGLE_SHEET_ID
        )

        # TODO: Initialiser cards_by_category et upgrade_cards_by_category
        # en lisant depuis Google Sheets

        # Initialiser les managers
        self.drawing_manager = DrawingManager(...)
        self.vault_manager = VaultManager(...)
        self.trading_manager = TradingManager(...)

# Instance globale
card_system = CardSystemService()
```

#### B. Compléter les routes API

Dans chaque fichier de `backend/app/api/`, remplacez les TODO par des appels aux services:

**Exemple dans `backend/app/api/draw.py`:**

```python
from ..services.storage_service import card_system

@router.post("/daily", response_model=Card)
async def perform_daily_draw(current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]

    # Vérifier que l'utilisateur peut tirer
    can_draw = await asyncio.to_thread(
        card_system.drawing_manager.can_perform_daily_draw,
        user_id
    )

    if not can_draw:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous avez déjà effectué votre tirage journalier aujourd'hui"
        )

    # Effectuer le tirage
    drawn_cards = await asyncio.to_thread(
        card_system.drawing_manager.draw_cards,
        1
    )

    # Enregistrer le tirage
    await asyncio.to_thread(
        card_system.drawing_manager.record_daily_draw,
        user_id
    )

    # TODO: Ajouter la carte à la collection, vérifier si découverte, etc.

    return drawn_cards[0]
```

### Étape 3: Développer le Frontend

#### A. Créer la structure de base

**1. Créer `frontend/src/main.tsx`:**

```tsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'react-hot-toast'
import App from './App'
import './index.css'

const queryClient = new QueryClient()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <QueryClientProvider client={queryClient}>
        <App />
        <Toaster position="top-right" />
      </QueryClientProvider>
    </BrowserRouter>
  </React.StrictMode>,
)
```

**2. Créer `frontend/src/index.css`:**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  body {
    @apply font-sans antialiased;
  }

  h1, h2, h3, h4, h5, h6 {
    @apply font-display;
  }
}

@layer components {
  .card {
    @apply bg-dark-800 rounded-lg shadow-lg p-4 border border-dark-700;
  }

  .btn-primary {
    @apply bg-primary hover:bg-primary-600 text-white font-medium px-4 py-2 rounded-lg transition-colors;
  }

  .btn-secondary {
    @apply bg-secondary hover:bg-secondary-600 text-white font-medium px-4 py-2 rounded-lg transition-colors;
  }
}
```

**3. Créer le système d'authentification:**

`frontend/src/services/auth.ts`:

```typescript
import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL

export interface User {
  user_id: number
  username: string
  discriminator: string
  global_name?: string
  avatar?: string
}

export interface AuthResponse {
  access_token: string
  token_type: string
  user: User
  expires_in: number
}

export const authService = {
  async login(code: string): Promise<AuthResponse> {
    const response = await axios.get(`${API_URL}/api/auth/discord/callback`, {
      params: { code }
    })

    // Sauvegarder le token
    localStorage.setItem('access_token', response.data.access_token)

    return response.data
  },

  async getMe(): Promise<User> {
    const token = localStorage.getItem('access_token')
    const response = await axios.get(`${API_URL}/api/auth/me`, {
      headers: { Authorization: `Bearer ${token}` }
    })
    return response.data
  },

  logout() {
    localStorage.removeItem('access_token')
  },

  getToken(): string | null {
    return localStorage.getItem('access_token')
  },

  isAuthenticated(): boolean {
    return !!this.getToken()
  }
}
```

**4. Créer le store d'authentification (Zustand):**

`frontend/src/stores/authStore.ts`:

```typescript
import { create } from 'zustand'
import { User } from '../services/auth'

interface AuthState {
  user: User | null
  token: string | null
  setAuth: (user: User, token: string) => void
  clearAuth: () => void
  isAuthenticated: () => boolean
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  token: localStorage.getItem('access_token'),

  setAuth: (user, token) => {
    localStorage.setItem('access_token', token)
    set({ user, token })
  },

  clearAuth: () => {
    localStorage.removeItem('access_token')
    set({ user: null, token: null })
  },

  isAuthenticated: () => !!get().token,
}))
```

**5. Créer l'App principale:**

`frontend/src/App.tsx`:

```tsx
import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from './stores/authStore'

// Pages (à créer)
import Home from './pages/Home'
import Gallery from './pages/Gallery'
import Draw from './pages/Draw'
import Trade from './pages/Trade'
import Profile from './pages/Profile'
import AuthCallback from './pages/AuthCallback'

// Layout (à créer)
import Layout from './components/layout/Layout'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated())

  if (!isAuthenticated) {
    return <Navigate to="/" replace />
  }

  return <>{children}</>
}

function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Home />} />
        <Route path="/auth/callback" element={<AuthCallback />} />

        {/* Routes protégées */}
        <Route path="/gallery" element={
          <ProtectedRoute>
            <Gallery />
          </ProtectedRoute>
        } />
        <Route path="/draw" element={
          <ProtectedRoute>
            <Draw />
          </ProtectedRoute>
        } />
        <Route path="/trade" element={
          <ProtectedRoute>
            <Trade />
          </ProtectedRoute>
        } />
        <Route path="/profile" element={
          <ProtectedRoute>
            <Profile />
          </ProtectedRoute>
        } />
      </Route>
    </Routes>
  )
}

export default App
```

### Étape 4: Pages à Créer

Créez ces pages dans `frontend/src/pages/`:

1. **Home.tsx** - Page d'accueil avec présentation + bouton "Se connecter avec Discord"
2. **AuthCallback.tsx** - Gère le callback OAuth2 Discord
3. **Gallery.tsx** - Galerie de cartes avec filtres
4. **Draw.tsx** - Interface de tirage (journalier + sacrificiel)
5. **Trade.tsx** - Système d'échanges (tableau + direct)
6. **Profile.tsx** - Profil utilisateur avec statistiques

### Étape 5: Composants à Créer

Créez ces composants dans `frontend/src/components/`:

#### Cards
- `CardItem.tsx` - Affichage d'une carte individuelle
- `CardGrid.tsx` - Grille de cartes
- `CardModal.tsx` - Vue détaillée d'une carte
- `CardFlipAnimation.tsx` - Animation de tirage

#### Layout
- `Layout.tsx` - Layout principal avec header/footer
- `Header.tsx` - Navigation
- `Footer.tsx` - Footer

#### UI
- `Button.tsx` - Boutons réutilisables
- `Modal.tsx` - Modales
- `Loader.tsx` - Spinners de chargement

### Étape 6: Tester

```bash
# Terminal 1 - Backend
cd backend
uvicorn app.main:app --reload

# Terminal 2 - Frontend
cd frontend
npm run dev
```

Ouvrez `http://localhost:5173` dans votre navigateur.

## 📚 Ressources

- **Discord Developer Portal**: https://discord.com/developers/applications
- **FastAPI Docs**: https://fastapi.tiangolo.com/
- **React Query**: https://tanstack.com/query/latest
- **Framer Motion**: https://www.framer.com/motion/
- **TailwindCSS**: https://tailwindcss.com/

## 🎯 Prochaines Étapes Recommandées

1. ✅ **Implémenter les services backend** (priority 1)
2. ✅ **Créer la page d'accueil et l'authentification** (priority 1)
3. ✅ **Créer la galerie de cartes** (priority 2)
4. ✅ **Implémenter les tirages** (priority 2)
5. ✅ **Créer le système d'échanges** (priority 3)
6. ✅ **Ajouter les WebSockets pour temps réel** (priority 3)
7. ✅ **Déployer sur Render.com** (priority 4)

## 💡 Conseils

- Commencez par l'authentification - c'est la base de tout
- Testez chaque endpoint API avec FastAPI Docs (`http://localhost:8000/docs`)
- Utilisez React Query pour gérer le cache et les états de chargement
- Ajoutez des animations progressivement avec Framer Motion
- Gardez le design cohérent avec le thème fantastique

Bon développement ! 🚀✨
