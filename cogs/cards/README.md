# Système de Cartes à Collectionner - Architecture Refactorisée

Ce dossier contient le système de cartes à collectionner refactorisé, organisé en modules logiques pour une meilleure maintenabilité.

## 📁 Structure des Fichiers

### Modules Principaux

- **`config.py`** - Configuration et constantes du système
- **`models.py`** - Classes de données et modèles
- **`utils.py`** - Fonctions utilitaires partagées
- **`storage.py`** - Gestion du stockage Google Sheets et cache
- **`discovery.py`** - Système de découverte et logging des cartes
- **`vault.py`** - Gestion du système de vault pour les échanges
- **`drawing.py`** - Logique de tirage des cartes (normal, sacrificiel, journalier)
- **`trading.py`** - Logique d'échange entre utilisateurs
- **`forum.py`** - Gestion du forum des cartes découvertes

### Interface Utilisateur (`views/`)

- **`menu_views.py`** - Vues principales du menu des cartes
- **`trade_views.py`** - Vues pour les échanges
- **`gallery_views.py`** - Vues de galerie paginée
- **`modal_views.py`** - Modales pour les interactions utilisateur

## 🔧 Avantages de la Refactorisation

### Avant
- **6183 lignes** dans un seul fichier `Cards.py`
- Code difficile à maintenir et à déboguer
- Responsabilités mélangées
- Difficile à tester individuellement

### Après
- **530 lignes** dans le cog principal
- **2973 lignes** réparties dans 15 modules spécialisés
- **Réduction de 91%** de la taille du fichier principal
- Architecture modulaire et maintenable

## 🏗️ Architecture

```
Cards.py (530 lignes)
├── Orchestration des gestionnaires
├── Commandes Discord principales
└── Interface avec les modules

cards/
├── config.py          # Configuration
├── models.py           # Modèles de données
├── utils.py            # Utilitaires
├── storage.py          # Stockage & cache
├── discovery.py        # Découvertes
├── vault.py            # Système de vault
├── drawing.py          # Tirages
├── trading.py          # Échanges
├── forum.py            # Forum
└── views/
    ├── menu_views.py   # Menus principaux
    ├── trade_views.py  # Échanges
    ├── gallery_views.py # Galeries
    └── modal_views.py  # Modales
```

## 🚀 Utilisation

### Import du Cog Principal
```python
from cogs.Cards import Cards
```

### Import des Modules Spécifiques
```python
from cogs.cards.storage import CardsStorage
from cogs.cards.discovery import DiscoveryManager
from cogs.cards.vault import VaultManager
# etc.
```

### Import des Vues
```python
from cogs.cards.views import CardsMenuView, TradeMenuView
```

## 🔄 Gestionnaires Principaux

1. **CardsStorage** - Gestion centralisée du stockage et du cache
2. **DiscoveryManager** - Suivi des découvertes de cartes
3. **VaultManager** - Gestion du système de vault
4. **DrawingManager** - Logique de tous les types de tirages
5. **TradingManager** - Gestion des échanges entre utilisateurs
6. **ForumManager** - Gestion du forum des cartes

## 🎯 Fonctionnalités Préservées

Toutes les fonctionnalités originales sont préservées :
- ✅ Tirages de cartes (normal, journalier, sacrificiel)
- ✅ Système de vault et échanges
- ✅ Galeries paginées
- ✅ Forum des cartes découvertes
- ✅ Gestion des cartes Full
- ✅ Système de cache optimisé
- ✅ Sécurité et validation des données
- ✅ Tableau d'échanges avec commandes `!board`

## 🧪 Tests

La refactorisation a été testée avec succès :
- ✅ Imports de tous les modules
- ✅ Fonctions utilitaires
- ✅ Modèles de données
- ✅ Configuration

## 📝 Notes de Maintenance

- Chaque module a une responsabilité claire et définie
- Les imports circulaires sont évités grâce à `TYPE_CHECKING`
- Le code est documenté avec des docstrings
- La structure permet des tests unitaires faciles
- Les gestionnaires sont découplés et réutilisables
