# 📋 TODO - Citadelle Cards Web

## ✅ Complété

### Backend
- [x] Structure du projet backend
- [x] Configuration (config.py, security.py, dependencies.py)
- [x] Authentification Discord OAuth2 complète
- [x] Service CardSystemService (réutilisation du code du bot)
- [x] Routes API Cards (liste, catégories, détails)
- [x] Routes API Drawing (status et tirage journalier)
- [x] Routes API Drawing (status et aperçu sacrificiel)
- [x] Routes API User (collection, vault)
- [x] Modèles Pydantic complets

### Frontend
- [x] Configuration Vite + React + TypeScript
- [x] Configuration TailwindCSS avec thème fantastique
- [x] Dépendances installées

### Documentation
- [x] README.md principal
- [x] GETTING_STARTED.md détaillé
- [x] DEPLOYMENT.md pour Render.com

## 🔨 En Cours

### Backend
- [ ] **Route POST /api/draw/sacrificial** (effectuer le tirage sacrificiel)
  - Réserver le tirage
  - Retirer les 5 cartes de la collection
  - Tirer 5 nouvelles cartes
  - Ajouter les nouvelles cartes
  - Retourner les cartes obtenues

- [ ] **Routes API Trade** (toutes les routes sont en TODO)
  - GET /api/trade/board (liste des offres)
  - POST /api/trade/board (créer une offre)
  - DELETE /api/trade/board/{id} (retirer une offre)
  - POST /api/trade/board/{id}/accept (accepter une offre)
  - POST /api/trade/direct (échange direct)
  - GET /api/trade/history (historique)
  - GET /api/trade/weekly-limit (limite)
  - POST /api/trade/vault/exchange (échange de vault)

- [ ] **Méthodes de collection dans CardSystemService**
  - `_user_has_card()` - Vérification de possession
  - `_add_card_to_user()` - Ajout de carte
  - `_remove_card_from_user()` - Retrait de carte
  - `get_user_collection()` - Récupération complète

### Frontend - MVP
- [x] Version minimaliste pour tester l'authentification (en cours)

## 🎯 À Faire - Backend (Priority 2)

### Compléter les Routes Draw
```python
# backend/app/api/draw.py
@router.post("/sacrificial", response_model=List[Card])
async def perform_sacrificial_draw(current_user: dict):
    # 1. Réserver le tirage
    # 2. Récupérer les 5 cartes sélectionnées
    # 3. Retirer ces cartes de la collection
    # 4. Tirer 5 nouvelles cartes
    # 5. Ajouter les nouvelles cartes
    # 6. Retourner les cartes tirées
```

### Compléter les Routes Trade
```python
# backend/app/api/trade.py
# Implémenter toutes les routes en utilisant card_system.trading_manager
```

### Améliorer CardSystemService
```python
# backend/app/services/cards_service.py
def _user_has_card(self, user_id: int, category: str, name: str) -> bool:
    # Lire Google Sheets et chercher la carte de l'utilisateur
    pass

def _add_card_to_user(self, user_id: int, category: str, name: str) -> bool:
    # Ajouter une ligne dans Google Sheets
    pass

def _remove_card_from_user(self, user_id: int, category: str, name: str) -> bool:
    # Retirer une ligne dans Google Sheets
    pass

async def get_user_collection(self, user_id: int) -> Dict[str, Any]:
    # Récupérer toutes les cartes de l'utilisateur
    # Compter les exemplaires
    # Calculer les statistiques
    pass
```

## 🎨 À Faire - Frontend (Priority 1)

### Phase 1: MVP Fonctionnel ✅ (EN COURS)
- [x] Architecture de base (main.tsx, App.tsx, index.css)
- [x] Services API et Auth
- [x] Store Zustand pour l'authentification
- [x] Page d'accueil avec bouton Discord
- [x] Page AuthCallback pour OAuth2
- [x] Layout de base
- [ ] **TESTER L'AUTHENTIFICATION**

### Phase 2: Pages Principales
- [ ] **Page Gallery** (`src/pages/Gallery.tsx`)
  - Grille de cartes avec filtres par catégorie
  - Barre de recherche
  - Indicateurs de possession (si connecté)
  - Modal de détails de carte

- [ ] **Page Draw** (`src/pages/Draw.tsx`)
  - Section tirage journalier
    - Bouton "Tirer une carte"
    - Animation de reveal
    - Cooldown countdown
  - Section tirage sacrificiel
    - Affichage des 5 cartes qui seront sacrifiées
    - Bouton de confirmation
    - Animation de tirage multiple
    - Cooldown countdown

- [ ] **Page Profile** (`src/pages/Profile.tsx`)
  - Informations utilisateur Discord
  - Statistiques (cartes possédées, tirages, échanges)
  - Collection personnelle
  - Progression par catégorie

- [ ] **Page Trade** (`src/pages/Trade.tsx`)
  - Tableau d'échanges public
    - Liste des offres
    - Bouton "Proposer un échange"
  - Interface d'échange direct
  - Historique des échanges
  - Limite hebdomadaire

### Phase 3: Composants Réutilisables
- [ ] **CardItem** (`src/components/cards/CardItem.tsx`)
  - Affichage d'une carte
  - Badge de rareté (couleur selon catégorie)
  - Badge "Full" si applicable
  - Hover effects

- [ ] **CardGrid** (`src/components/cards/CardGrid.tsx`)
  - Grille responsive
  - Chargement lazy
  - Skeleton loaders

- [ ] **CardModal** (`src/components/cards/CardModal.tsx`)
  - Vue détaillée d'une carte
  - Informations (découvreur, date)
  - Boutons d'action (échanger, vault)

- [ ] **DrawAnimation** (`src/components/cards/DrawAnimation.tsx`)
  - Animation flip de carte
  - Particules selon rareté
  - Sound effects (optionnel)

- [ ] **Navigation** (`src/components/layout/Header.tsx`)
  - Menu principal
  - Avatar utilisateur
  - Bouton déconnexion

### Phase 4: Hooks Personnalisés
```typescript
// src/hooks/useCards.ts
export const useCards = (category?: string) => {
  // React Query pour fetcher les cartes
}

// src/hooks/useUserCollection.ts
export const useUserCollection = () => {
  // React Query pour la collection
}

// src/hooks/useDraw.ts
export const useDraw = () => {
  // Hooks pour les tirages
}

// src/hooks/useTrade.ts
export const useTrade = () => {
  // Hooks pour les échanges
}
```

### Phase 5: Animations et Polish
- [ ] Animations Framer Motion
  - Page transitions
  - Card flip animations
  - Particles pour tirages rares
  - Hover effects élégants

- [ ] Responsive Design
  - Mobile (< 768px)
  - Tablet (768px - 1024px)
  - Desktop (> 1024px)

- [ ] Dark Mode (déjà le thème par défaut)
  - Assurer le contraste
  - Tester la lisibilité

- [ ] Loading States
  - Skeletons
  - Spinners
  - Progress bars

- [ ] Error Handling
  - Messages d'erreur clairs
  - Retry buttons
  - Fallback UI

## 🚀 À Faire - Déploiement (Priority 3)

### Préparation
- [ ] Créer un repo GitHub séparé pour le site
- [ ] Configurer les variables d'environnement de production
- [ ] Tester localement avec les vraies credentials

### Render.com
- [ ] Déployer le backend
  - Configurer le service web
  - Ajouter toutes les variables d'environnement
  - Tester les endpoints

- [ ] Déployer le frontend
  - Configurer le static site
  - Ajouter les variables de build
  - Tester l'authentification

### Post-Déploiement
- [ ] Configurer Discord OAuth2 avec l'URL de production
- [ ] Tester tous les flows (auth, tirages, échanges)
- [ ] Monitoring et logs
- [ ] Optimisations de performance

## 💡 Fonctionnalités Bonus (Priority 4)

### WebSocket pour Temps Réel
```python
# backend/app/websocket/manager.py
class ConnectionManager:
    # Gérer les connexions WebSocket
    # Notifications d'échanges
    # Mises à jour en temps réel
```

### Achievements System
- [ ] Système de badges
  - "Premier tirage"
  - "Collectionneur (X cartes)"
  - "Découvreur"
  - "Trader actif"

### Leaderboards
- [ ] Plus grand collectionneur
- [ ] Plus de découvertes
- [ ] Plus d'échanges

### Progressive Web App (PWA)
- [ ] Service Worker
- [ ] Manifest.json
- [ ] Notifications push
- [ ] Mode offline (lecture seule)

### Analytics
- [ ] Graphiques de progression
- [ ] Statistiques de rareté
- [ ] Tendances d'échanges

## 📝 Notes Importantes

### Limitations Actuelles
1. **Collection utilisateur** - Les méthodes `_add_card_to_user` et `_remove_card_from_user` retournent True sans vraiment modifier Google Sheets. Il faut implémenter la logique réelle.

2. **Découvertes** - Le système de découvertes n'est pas encore implémenté dans les routes API.

3. **Trading** - Toutes les routes de trading sont en TODO.

4. **WebSocket** - Pas encore implémenté pour les notifications temps réel.

### Priorités de Développement
1. **URGENT**: Compléter les méthodes de collection dans CardSystemService
2. **HIGH**: Implémenter les routes de trading
3. **MEDIUM**: Compléter le frontend (Gallery, Draw, Profile, Trade)
4. **LOW**: Animations et polish
5. **BONUS**: WebSocket, PWA, Achievements

### Tests à Effectuer
- [ ] Authentification Discord
- [ ] Tirage journalier (vérifier cooldown)
- [ ] Tirage sacrificiel (vérifier 5 cartes)
- [ ] Affichage de la galerie
- [ ] Système d'échanges
- [ ] Limite hebdomadaire d'échanges
- [ ] Vault (dépôt/retrait)

---

**Dernière mise à jour**: 2025-10-12
**Statut global**: Backend 70% - Frontend 10% - Documentation 100%
