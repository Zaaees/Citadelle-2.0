# Système de Vérification Automatique des Conversions vers les Cartes Full

## 📋 Résumé

Ce document décrit l'implémentation d'un système de vérification automatique des conversions vers les cartes Full qui se déclenche après chaque tirage (journalier, sacrificiel) et chaque échange de cartes.

## 🎯 Objectif

Automatiser la vérification et la conversion des cartes normales vers leurs versions Full lorsque l'utilisateur possède le nombre requis d'exemplaires (actuellement 5 cartes "Élèves" → 1 carte "Élèves (Full)").

## 🔧 Implémentation

### Composants Modifiés

#### 1. **Cog Principal (`cogs/Cards.py`)**

**Nouvelles méthodes ajoutées :**
- `_mark_user_for_upgrade_check(user_id)` : Marque un utilisateur pour vérification d'upgrade
- `auto_check_upgrades(interaction, user_id, notification_channel_id)` : Vérification automatique pour un utilisateur
- `process_all_pending_upgrade_checks(interaction, notification_channel_id)` : Traite toutes les vérifications en attente

**Modifications :**
- `add_card_to_user()` : Marque automatiquement l'utilisateur pour vérification après ajout de carte
- Initialisation d'un set `_users_needing_upgrade_check` pour tracker les utilisateurs

#### 2. **Gestionnaire de Tirages (`cogs/cards/drawing.py`)**

**Modifications :**
- `record_daily_draw()` : Marque l'utilisateur pour vérification après tirage journalier
- `record_sacrificial_draw()` : Marque l'utilisateur pour vérification après tirage sacrificiel

#### 3. **Gestionnaire d'Échanges (`cogs/cards/trading.py`)**

**Modifications :**
- `safe_exchange()` : Marque les deux utilisateurs pour vérification après échange de cartes
- `execute_full_vault_trade()` : Marque les deux utilisateurs pour vérification après échange de vaults
- `record_weekly_exchange()` : Marque l'utilisateur pour vérification après échange hebdomadaire

#### 4. **Vues d'Interface (`cogs/cards/views/`)**

**Modifications :**
- `menu_views.py` : Appel de `process_all_pending_upgrade_checks()` après tirages
- `trade_views.py` : Appel de `process_all_pending_upgrade_checks()` après échanges de vaults

## 🔄 Flux de Fonctionnement

### 1. Déclenchement Automatique

Le système se déclenche automatiquement après :
- ✅ Tirage journalier (3 cartes)
- ✅ Tirage sacrificiel (1 carte rare)
- ✅ Échange de cartes individuelles
- ✅ Échange complet de vaults
- ✅ Échanges hebdomadaires
- ✅ Tout ajout de carte à l'inventaire

### 2. Processus de Vérification

1. **Marquage** : L'utilisateur est ajouté au set `_users_needing_upgrade_check`
2. **Traitement** : `process_all_pending_upgrade_checks()` est appelé
3. **Vérification** : Pour chaque utilisateur marqué :
   - Récupération de son inventaire
   - Comptage des cartes par type
   - Vérification des seuils de conversion
   - Conversion automatique si seuil atteint
4. **Nettoyage** : Le set des utilisateurs en attente est vidé

### 3. Logique de Conversion

```python
# Seuils actuels
upgrade_thresholds = {"Élèves": 5}

# Exemple : 5 cartes "Élèves/Inès" → 1 carte "Élèves/Inès (Full)"
```

## 📊 Points de Déclenchement

| Action | Méthode | Utilisateurs Marqués |
|--------|---------|---------------------|
| Tirage journalier | `record_daily_draw()` | Utilisateur qui tire |
| Tirage sacrificiel | `record_sacrificial_draw()` | Utilisateur qui tire |
| Échange de cartes | `safe_exchange()` | Les 2 utilisateurs |
| Échange de vaults | `execute_full_vault_trade()` | Les 2 utilisateurs |
| Échange hebdomadaire | `record_weekly_exchange()` | Utilisateur qui échange |
| Ajout de carte | `add_card_to_user()` | Utilisateur qui reçoit |

## 🛡️ Sécurité et Robustesse

### Gestion d'Erreurs
- Toutes les vérifications sont dans des blocs `try/except`
- Les erreurs de conversion n'interrompent pas les opérations principales
- Logging détaillé pour le débogage

### Prévention des Doublons
- Utilisation d'un `set()` pour éviter les vérifications multiples du même utilisateur
- Nettoyage automatique après traitement

### Atomicité
- Les conversions utilisent le système de rollback existant
- Les vérifications ne modifient pas l'état en cas d'erreur

## 🔍 Logging et Débogage

Le système génère des logs détaillés :
```
[AUTO_UPGRADE] Utilisateur 12345 marqué pour vérification d'upgrade
[AUTO_UPGRADE] Vérification automatique des conversions terminée pour l'utilisateur 12345
[UPGRADE] Conversion réussie: 5x Élèves/Inès → 1x Élèves/Inès (Full) pour l'utilisateur 12345
```

## 🧪 Tests

Un script de test `test_auto_upgrade.py` a été créé pour valider le fonctionnement :
- Simulation de tirages journaliers et sacrificiels
- Simulation d'échanges de cartes
- Vérification du marquage et du traitement des utilisateurs

## 📈 Avantages

1. **Automatisation Complète** : Plus besoin d'intervention manuelle
2. **Déclenchement Universel** : Fonctionne après toute modification d'inventaire
3. **Performance Optimisée** : Traitement groupé des vérifications
4. **Robustesse** : Gestion d'erreurs et logging complet
5. **Transparence** : L'utilisateur est notifié des conversions

## 🔮 Évolutions Futures

- Extension à d'autres catégories de cartes
- Seuils de conversion configurables
- Interface d'administration pour gérer les conversions
- Statistiques de conversion par utilisateur

## ⚠️ Notes Importantes

- Le système respecte les seuils existants (5 cartes Élèves → 1 Full)
- Les notifications sont envoyées dans le salon configuré (ID: 1361993326215172218)
- La logique de conversion existante est préservée
- Aucun impact sur les performances grâce au traitement groupé
