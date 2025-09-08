# Plan d'Améliorations Système - Citadelle 2.0

## 📋 Instructions d'usage

**Pour l'utilisateur** : Dis "fais la prochaine amélioration système" et Claude fera automatiquement la prochaine amélioration non terminée de cette liste, puis la marquera comme ✅ TERMINÉE.

**Pour Claude** : 
1. Lis ce fichier pour identifier la prochaine amélioration avec status ⏳ EN ATTENTE
2. Fais UNIQUEMENT cette amélioration (ne pas en faire plusieurs à la fois)
3. Une fois terminée, marque-la comme ✅ TERMINÉE avec la date/heure
4. Ajoute les détails de ce qui a été fait sous la section "Détails d'implémentation"
5. Commit et push automatiquement les changements selon CLAUDE.md

---

## 🎯 Plan d'Améliorations (par ordre de priorité)

### Priorité 1 - Performance Critique

#### 1. Cache Google Sheets optimisé ⏳ EN ATTENTE
**Problème** : Cache de 5 secondes trop court, trop d'appels API
**Action** : Passer `CACHE_VALIDITY_DURATION` à 60 secondes dans `config.py`
**Impact** : -90% d'appels Google Sheets
**Fichiers** : `cogs/cards/config.py`
**Détails d'implémentation** :
- [ ] À faire

#### 2. Async Google Sheets manquant ⏳ EN ATTENTE
**Problème** : Appels Google Sheets bloquants dans `Cards.py`
**Action** : Wrapper tous les appels avec `asyncio.to_thread()`
**Impact** : Évite le blocage du bot
**Fichiers** : `cogs/Cards.py` (lignes avec `get_all_values`, `append_row`, `update`)
**Détails d'implémentation** :
- [ ] À faire

#### 3. Constants globales ⏳ EN ATTENTE
**Problème** : IDs hardcodés dans le code
**Action** : Déplacer tous les IDs magiques vers `config.py` ou variables d'environnement
**Impact** : Configuration plus claire
**Fichiers** : `cogs/cards/views/menu_views.py`, `cogs/cards/config.py`
**Détails d'implémentation** :
- [ ] À faire

### Priorité 2 - Architecture

#### 4. Factory pattern Google Sheets ⏳ EN ATTENTE
**Problème** : Code dupliqué d'initialisation Google Sheets
**Action** : Créer `utils/google_sheets_factory.py` avec classe réutilisable
**Impact** : Moins de duplication, maintenance plus facile
**Fichiers** : Nouveau `utils/google_sheets_factory.py`, refactor des cogs
**Détails d'implémentation** :
- [ ] À faire

#### 5. Gestionnaire d'erreurs centralisé ⏳ EN ATTENTE
**Problème** : Gestion d'erreurs Google Sheets différente partout
**Action** : Créer décorateur `@handle_sheets_errors` réutilisable
**Impact** : Gestion d'erreurs cohérente
**Fichiers** : Nouveau `utils/error_handlers.py`
**Détails d'implémentation** :
- [ ] À faire

#### 6. Configuration centralisée ⏳ EN ATTENTE
**Problème** : Variables d'environnement éparpillées
**Action** : Créer classe `Settings` avec validation
**Impact** : Configuration plus robuste
**Fichiers** : Nouveau `config/settings.py`
**Détails d'implémentation** :
- [ ] À faire

### Priorité 3 - Maintenabilité

#### 7. Batch Google Sheets ⏳ EN ATTENTE
**Problème** : `append_row` individuels inefficaces
**Action** : Remplacer par `append_rows` et `batch_update` où possible
**Impact** : Moins d'appels API
**Fichiers** : Tous les cogs utilisant Google Sheets
**Détails d'implémentation** :
- [ ] À faire

#### 8. Type hints complets ⏳ EN ATTENTE
**Problème** : Fonctions sans type hints
**Action** : Ajouter type hints manquants
**Impact** : Meilleure maintenabilité
**Fichiers** : Tous les fichiers Python
**Détails d'implémentation** :
- [ ] À faire

#### 9. Logging standardisé ⏳ EN ATTENTE
**Problème** : Formats de logs inconsistants
**Action** : Standardiser les préfixes et formats de logs
**Impact** : Debugging plus facile
**Fichiers** : Tous les cogs
**Détails d'implémentation** :
- [ ] À faire

### Priorité 4 - Fonctionnalités

#### 10. Retry avec backoff ⏳ EN ATTENTE
**Problème** : Pas de retry sur échecs Google Sheets
**Action** : Ajouter retry automatique avec backoff exponentiel
**Impact** : Plus de robustesse
**Fichiers** : `utils/retry_handler.py`
**Détails d'implémentation** :
- [ ] À faire

#### 11. Health checks détaillés ⏳ EN ATTENTE
**Problème** : `/health` basique
**Action** : Ajouter métriques Google Sheets, cache, etc.
**Impact** : Meilleur monitoring
**Fichiers** : `server_minimal.py`
**Détails d'implémentation** :
- [ ] À faire

#### 12. Migration f-strings ⏳ EN ATTENTE
**Problème** : Mélange `.format()` et f-strings
**Action** : Standardiser sur f-strings partout
**Impact** : Performance légère
**Fichiers** : Tous les fichiers Python
**Détails d'implémentation** :
- [ ] À faire

#### 13. Command cooldowns intelligents ⏳ EN ATTENTE
**Problème** : Cooldowns fixes
**Action** : Cooldowns adaptatifs selon la charge
**Impact** : Meilleure UX
**Fichiers** : Tous les cogs avec commandes
**Détails d'implémentation** :
- [ ] À faire

#### 14. Validation des données ⏳ EN ATTENTE
**Problème** : Peu de validation inputs utilisateur
**Action** : Ajouter validateurs pour IDs Discord, formats, etc.
**Impact** : Moins d'erreurs runtime
**Fichiers** : Nouveau `utils/validators.py`
**Détails d'implémentation** :
- [ ] À faire

#### 15. Cleanup automatique ⏳ EN ATTENTE
**Problème** : Risque de fuites de connexions
**Action** : Context managers pour Google Sheets
**Impact** : Gestion ressources plus propre
**Fichiers** : `utils/context_managers.py`
**Détails d'implémentation** :
- [ ] À faire

---

## 📊 Statistiques

- **Total améliorations** : 15
- **Terminées** : 0
- **En cours** : 0
- **En attente** : 15

---

## 📝 Historique des modifications

*Les modifications terminées apparaîtront ici avec date/heure et détails d'implémentation*