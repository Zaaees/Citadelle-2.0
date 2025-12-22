# ⚡ Quick Start - Tester l'Authentification

Guide de démarrage ultra-rapide pour tester l'authentification Discord.

## ✅ Ce qui est prêt

- ✅ Backend API avec authentification Discord OAuth2
- ✅ Frontend React avec système d'auth complet
- ✅ Page d'accueil et callback OAuth2
- ✅ Layout avec header/footer
- ✅ State management (Zustand)
- ✅ Persistance de la session

## 🚀 Étapes de Test (15 minutes)

### 1. Configuration Discord OAuth2 (5 min)

1. Aller sur https://discord.com/developers/applications
2. Sélectionner votre application (ou créer une nouvelle)
3. Dans "OAuth2" → "General":
   - **Redirect URLs**: Ajouter `http://localhost:5173/auth/callback`
   - Sauvegarder
4. Copier le **Client ID** et **Client Secret**

### 2. Configuration Backend (3 min)

```bash
cd Site/backend

# Créer .env (si pas déjà fait)
cp .env.example .env
```

Éditer `backend/.env` et remplir:
```bash
DISCORD_CLIENT_ID=418825336336416768
DISCORD_CLIENT_SECRET=uTTudXcvXDQgxm2IiSiQNq5fFqM0dnFr
DISCORD_REDIRECT_URI=http://localhost:5173/auth/callback

# Utiliser les mêmes credentials que le bot
SERVICE_ACCOUNT_JSON={"type": "service_account", ...}
GOOGLE_SHEET_ID=161mnYzQH-r8uj6PnYcX0o5JhtA1yGN-_3lj_VTXrt0U

# JWT (générer une clé aléatoire forte)
JWT_SECRET_KEY=changez_moi_avec_une_cle_secrete_forte_et_aleatoire

FRONTEND_URL=http://localhost:5173
```

**Important**: Réutilisez les mêmes `SERVICE_ACCOUNT_JSON` et `GOOGLE_SHEET_ID` que votre bot Discord !

### 3. Configuration Frontend (2 min)

```bash
cd Site/frontend

# Créer .env.local
cp .env.example .env.local
```

Éditer `frontend/.env.local`:
```bash
VITE_API_URL=http://localhost:8000
VITE_DISCORD_CLIENT_ID=votre_client_id_ici
VITE_DISCORD_REDIRECT_URI=http://localhost:5173/auth/callback
VITE_WS_URL=ws://localhost:8000/ws
VITE_ENVIRONMENT=development
```

### 4. Installation des Dépendances (3 min)

**Backend:**
```bash
cd Site/backend
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate

pip install -r requirements.txt
```

**Frontend:**
```bash
cd Site/frontend
npm install
```

### 5. Lancement (2 min)

**Terminal 1 - Backend:**
```bash
cd Site/backend
source venv/bin/activate  # ou venv\Scripts\activate sur Windows
uvicorn app.main:app --reload
```

Vous devriez voir:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     🚀 Citadelle Cards API v1.0.0 démarré
```

**Terminal 2 - Frontend:**
```bash
cd Site/frontend
npm run dev
```

Vous devriez voir:
```
  VITE v5.0.8  ready in 500 ms

  ➜  Local:   http://localhost:5173/
```

### 6. Test de l'Authentification 🎉

1. **Ouvrir** `http://localhost:5173` dans votre navigateur

2. **Page d'accueil**: Vous devriez voir une belle page avec:
   - Logo Citadelle Cards
   - Bouton "Se connecter avec Discord"
   - Description des fonctionnalités
   - Catégories de rareté

3. **Cliquer** sur "Se connecter avec Discord"
   - Vous êtes redirigé vers Discord
   - Discord vous demande d'autoriser l'application
   - Cliquez sur "Autoriser"

4. **Redirection**: Vous revenez sur le site
   - Page de chargement brève
   - Toast de succès "Bienvenue, [Votre nom] !"
   - Page d'accueil personnalisée

5. **Vérifier l'authentification**:
   - Header affiche votre avatar Discord
   - Votre nom d'utilisateur est visible
   - Bouton "Déconnexion" disponible
   - Message de bienvenue personnalisé

6. **Tester la déconnexion**:
   - Cliquer sur "Déconnexion"
   - Toast "Déconnexion réussie"
   - Retour à la page d'accueil non-authentifiée

## 🔍 Vérifications de l'API

Pendant que le backend tourne, vous pouvez tester les endpoints:

**Documentation interactive:**
http://localhost:8000/docs

**Health check:**
http://localhost:8000/health

**Endpoints disponibles:**
- GET `/api/auth/discord` - URL d'autorisation Discord
- GET `/api/auth/discord/callback?code=...` - Callback OAuth2
- GET `/api/auth/me` - Informations utilisateur (nécessite token)
- GET `/api/cards` - Liste des cartes
- GET `/api/cards/categories` - Catégories de rareté

## 🐛 Dépannage

### Backend ne démarre pas

**Erreur: `ModuleNotFoundError: No module named 'cogs'`**

Le backend essaie d'importer le code du bot depuis `cogs/cards/`. Assurez-vous que:
1. Le dossier `Site/` est bien dans `Citadelle-2.0/` (à côté de `cogs/`)
2. La structure est: `Citadelle-2.0/cogs/` et `Citadelle-2.0/Site/backend/`

**Erreur: `ServiceAccountCredentials not found`**

```bash
pip install oauth2client
```

### Frontend ne démarre pas

**Erreur: `Cannot find module`**

```bash
cd Site/frontend
rm -rf node_modules
npm install
```

**Erreur: Variables d'environnement**

Vérifiez que `.env.local` existe et contient toutes les variables.

### L'authentification échoue

1. **Vérifier la console du navigateur** (F12)
2. **Vérifier les logs du backend** dans le terminal
3. **Vérifier que Discord Redirect URI** est exactement `http://localhost:5173/auth/callback`
4. **Vérifier que CORS** est configuré (déjà fait dans le backend)

### La session n'est pas persistée

Vérifiez que le localStorage fonctionne:
1. Ouvrir DevTools (F12)
2. Application → Local Storage
3. Chercher `citadelle-auth-storage`

## 📝 Logs à Surveiller

**Backend:**
```
INFO:     🚀 Citadelle Cards API v1.0.0 démarré
INFO:     📝 Environment: development
INFO:     🔗 Frontend URL: http://localhost:5173
INFO:     🔄 Initialisation du CardSystemService...
INFO:     ✅ CardSystemService initialisé avec succès
```

**Frontend (console du navigateur):**
```
✨ Citadelle Cards loaded
🔐 Auth store initialized
```

## ✨ Prochaines Étapes

Maintenant que l'authentification fonctionne:

1. **Consulter TODO.md** pour voir ce qu'il reste à faire
2. **Lire GETTING_STARTED.md** pour les détails complets
3. **Développer les pages** Gallery, Draw, Trade
4. **Déployer sur Render.com** (voir DEPLOYMENT.md)

## 🎉 Succès !

Si vous voyez votre avatar Discord dans le header et que la déconnexion fonctionne, **félicitations** ! L'authentification est opérationnelle. 🎊

Le site est maintenant prêt pour le développement des fonctionnalités principales (galerie, tirages, échanges).

---

**Besoin d'aide ?** Consultez `GETTING_STARTED.md` pour plus de détails ou `TODO.md` pour la liste complète des tâches.
