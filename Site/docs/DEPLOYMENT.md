# 🚀 Guide de Déploiement sur Render.com

Ce guide explique comment déployer le site Citadelle Cards sur Render.com.

## Prérequis

- Compte Render.com (gratuit)
- Code poussé sur GitHub (le dossier Site/ est dans .gitignore, créez un repo séparé)
- Variables d'environnement configurées

## Étape 1: Préparer le Code pour le Déploiement

### Backend

1. **Créer un fichier `render.yaml` à la racine de Site/**

```yaml
services:
  # Backend API
  - type: web
    name: citadelle-cards-api
    env: python
    region: frankfurt
    plan: free
    buildCommand: cd backend && pip install -r requirements.txt
    startCommand: cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT
    envVars:
      - key: PORT
        value: 10000
      - key: ENVIRONMENT
        value: production
      # Les autres variables seront ajoutées via le dashboard

  # Frontend Static Site
  - type: web
    name: citadelle-cards-web
    env: static
    region: frankfurt
    buildCommand: cd frontend && npm install && npm run build
    staticPublishPath: frontend/dist
    routes:
      - type: rewrite
        source: /*
        destination: /index.html
```

2. **Créer un repo GitHub séparé pour le site**

```bash
cd Site/
git init
git add .
git commit -m "Initial commit: Citadelle Cards Web"
git remote add origin https://github.com/votre-username/citadelle-cards-web.git
git push -u origin main
```

## Étape 2: Déployer sur Render.com

### Déploiement du Backend

1. Aller sur https://dashboard.render.com/
2. Cliquer sur "New +" → "Web Service"
3. Connecter votre repo GitHub
4. Configuration:
   - **Name**: `citadelle-cards-api`
   - **Region**: Frankfurt (ou Oregon)
   - **Branch**: `main`
   - **Root Directory**: `backend`
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Plan**: Free

5. **Ajouter les variables d'environnement:**

```
ENVIRONMENT=production
DEBUG=False

FRONTEND_URL=https://citadelle-cards-web.onrender.com

DISCORD_CLIENT_ID=your_discord_client_id
DISCORD_CLIENT_SECRET=your_discord_client_secret
DISCORD_REDIRECT_URI=https://citadelle-cards-web.onrender.com/auth/callback

JWT_SECRET_KEY=your_super_secret_jwt_key_change_this_in_production
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60

SERVICE_ACCOUNT_JSON={"type": "service_account", ...}
GOOGLE_SHEET_ID=your_google_sheet_id

LOG_LEVEL=INFO
```

6. Cliquer sur "Create Web Service"

Le backend sera disponible à: `https://citadelle-cards-api.onrender.com`

### Déploiement du Frontend

1. Sur Render Dashboard, cliquer sur "New +" → "Static Site"
2. Connecter le même repo GitHub
3. Configuration:
   - **Name**: `citadelle-cards-web`
   - **Branch**: `main`
   - **Root Directory**: `frontend`
   - **Build Command**: `npm install && npm run build`
   - **Publish Directory**: `dist`

4. **Ajouter les variables d'environnement de build:**

```
VITE_API_URL=https://citadelle-cards-api.onrender.com
VITE_DISCORD_CLIENT_ID=your_discord_client_id
VITE_DISCORD_REDIRECT_URI=https://citadelle-cards-web.onrender.com/auth/callback
VITE_WS_URL=wss://citadelle-cards-api.onrender.com/ws
VITE_ENVIRONMENT=production
```

5. Cliquer sur "Create Static Site"

Le frontend sera disponible à: `https://citadelle-cards-web.onrender.com`

## Étape 3: Configurer Discord OAuth2 pour Production

1. Aller sur [Discord Developer Portal](https://discord.com/developers/applications)
2. Sélectionner votre application
3. Dans "OAuth2" → "General":
   - Ajouter Redirect URL: `https://citadelle-cards-web.onrender.com/auth/callback`
4. Sauvegarder

## Étape 4: Configuration CORS

Le backend est déjà configuré pour accepter les requêtes du frontend en production grâce à `settings.FRONTEND_URL`.

Vérifiez dans `backend/app/core/config.py`:

```python
@property
def CORS_ORIGINS(self) -> List[str]:
    if self.ENVIRONMENT == "production":
        return [self.FRONTEND_URL]
    return [self.FRONTEND_URL, "http://localhost:5173", "http://127.0.0.1:5173"]
```

## Étape 5: Vérifications Post-Déploiement

### Tester le Backend

```bash
# Health check
curl https://citadelle-cards-api.onrender.com/health

# API documentation (si DEBUG=True)
# Ouvrir dans le navigateur: https://citadelle-cards-api.onrender.com/docs
```

### Tester le Frontend

1. Ouvrir `https://citadelle-cards-web.onrender.com`
2. Cliquer sur "Se connecter avec Discord"
3. Autoriser l'application
4. Vérifier que vous êtes bien authentifié

## Étape 6: Monitoring et Logs

### Logs Backend

1. Aller sur Render Dashboard → Votre service backend
2. Onglet "Logs" pour voir les logs en temps réel

### Logs Frontend

1. Aller sur Render Dashboard → Votre static site
2. Onglet "Logs" pour voir les logs de build

## Optimisations pour la Production

### Backend

1. **Activer les workers Gunicorn** (pour meilleures performances)

Modifier le Start Command:

```bash
gunicorn app.main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT
```

Ajouter dans `requirements.txt`:
```
gunicorn==21.2.0
```

2. **Activer le cache Redis** (optionnel, plan payant)

### Frontend

1. **Optimiser les assets**

Le build Vite optimise déjà automatiquement:
- Minification
- Tree-shaking
- Code splitting
- Lazy loading

2. **Activer le CDN Render** (automatique)

## Domaine Personnalisé (Optionnel)

### Pour le Frontend

1. Sur Render Dashboard → Votre static site
2. Onglet "Settings" → "Custom Domain"
3. Ajouter votre domaine (ex: `cards.citadelle.com`)
4. Configurer les DNS selon les instructions Render

### Pour le Backend (API)

1. Sur Render Dashboard → Votre web service
2. Onglet "Settings" → "Custom Domain"
3. Ajouter votre sous-domaine API (ex: `api-cards.citadelle.com`)
4. Configurer les DNS

⚠️ **Important**: Mettre à jour les variables d'environnement avec les nouveaux domaines!

## Mise à Jour du Site

### Déploiement Automatique

Render déploie automatiquement à chaque push sur la branche `main`:

```bash
git add .
git commit -m "feat: nouvelle fonctionnalité"
git push origin main
```

Le déploiement se fait automatiquement en ~2-5 minutes.

### Déploiement Manuel

Sur Render Dashboard → Votre service → "Manual Deploy" → "Deploy latest commit"

## Résolution de Problèmes

### Le backend ne démarre pas

1. Vérifier les logs
2. Vérifier que toutes les variables d'environnement sont définies
3. Vérifier que `SERVICE_ACCOUNT_JSON` est valide (JSON bien formaté)

### Erreur CORS

1. Vérifier que `FRONTEND_URL` est correctement défini dans le backend
2. Vérifier que `ENVIRONMENT=production`

### L'authentification Discord échoue

1. Vérifier que le `DISCORD_REDIRECT_URI` correspond exactement à l'URL configurée sur Discord
2. Vérifier que le Client ID et Client Secret sont corrects

### Le frontend ne se connecte pas à l'API

1. Vérifier que `VITE_API_URL` pointe vers le bon URL du backend
2. Ouvrir la console du navigateur pour voir les erreurs
3. Vérifier que le backend est bien déployé et fonctionne

## Coûts

### Plan Gratuit (Free Tier)

- **Backend**: 750 heures/mois (suffisant pour 1 instance)
- **Frontend**: Bande passante et builds illimités
- **Limitations**:
  - Le backend s'endort après 15 minutes d'inactivité
  - Premier démarrage peut prendre 30-60 secondes
  - 512 MB RAM pour le backend

### Plans Payants

Si vous avez besoin de plus de performances:
- **Starter ($7/mois)**: Backend toujours actif, 512 MB RAM
- **Standard ($25/mois)**: 2 GB RAM, scaling automatique

## Sécurité

### Checklist de Sécurité

- [ ] `DEBUG=False` en production
- [ ] `JWT_SECRET_KEY` est une clé forte et unique
- [ ] Les credentials Discord sont sécurisés
- [ ] `SERVICE_ACCOUNT_JSON` n'est pas exposé publiquement
- [ ] CORS est correctement configuré
- [ ] HTTPS est activé (automatique sur Render)

## Backup

Les données sont dans Google Sheets, donc pas de backup nécessaire pour la base de données. Assurez-vous simplement que:

1. Le code est versé sur GitHub
2. Les variables d'environnement sont sauvegardées dans un endroit sécurisé

---

🎉 Votre site est maintenant en ligne et accessible publiquement!
