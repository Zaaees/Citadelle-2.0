# TODO - Problèmes Identifiés dans Citadelle-2.0

**Date d'analyse**: 2025-11-22
**Date de dernière mise à jour**: 2025-11-22
**Total de problèmes**: 29
**Priorité**: 3 Critiques | 6 Élevés | 10 Moyens | 10 Faibles

## 📊 Statut des Corrections

**✅ COMPLÉTÉS (18/29 - 62%)**:
- **CRITICAL** (3/3): #1, #2, #3
- **HIGH** (5/6): #4, #5, #6, #7, #8, #15
- **MEDIUM** (7/10): #10, #11, #12, #14, #16, #17, #19
- **LOW** (2/10): #23, #26

**Détails des corrections:**
- **Batch 1** (session actuelle): #14, #19, #26 - Tasks init, validation, exception logging
- **Batch 2** (session actuelle): #17, #23 - IDs configurables, magic numbers → constantes
- **Batch 3** (session actuelle): #12, #15 - Rate limiting API, resource cleanup
- **Session précédente**: #1-#8, #10-#11, #16 - Sécurité, bugs critiques, imports

**⏳ RESTANTS (11/29 - 38%)**:
- **HIGH** (1/6): #9 - Cache cleanup avec LRU (refactoring architecture majeur)
- **MEDIUM** (3/10): #13, #18 - Checkpoints, max retries (implémentations complexes)
- **LOW** (8/10): #20-#22, #24-#25, #27-#29 - Type hints, docstrings, standardisation (refactoring extensif)

**Note**: Les issues restantes nécessitent des refactorings majeurs qui pourraient introduire des régressions. Les corrections effectuées couvrent tous les problèmes CRITIQUES et la majorité des HIGH/MEDIUM priority.

---

## 🔴 CRITIQUE - À corriger immédiatement

### 1. **SÉCURITÉ: Utilisation dangereuse de `eval()` sur des données non fiables**

**Fichiers concernés:**
- `cogs/scene_surveillance.py` - Ligne 128
- `cogs/validation.py` - Lignes 41, 42, 77, 78, 128, 129, 200

**Problème:**
Utilisation de `eval()` pour parser des données provenant de Google Sheets et des variables d'environnement. Cela crée une vulnérabilité d'injection de code critique.

**Impact:**
⚠️ Exécution de code arbitraire possible, compromission totale du système si un attaquant accède aux Google Sheets.

**Solution:**
```python
# ❌ AVANT:
service_account_json = eval(os.getenv('SERVICE_ACCOUNT_JSON'))
validated_by = eval(row_data[1]) if row_data[1] else []

# ✅ APRÈS:
import json
service_account_json = json.loads(os.getenv('SERVICE_ACCOUNT_JSON'))
validated_by = json.loads(row_data[1]) if row_data[1] else []
```

---

### 2. **BUG CRITIQUE: Variable utilisée avant d'être définie**

**Fichier:** `cogs/scene_surveillance.py` - Lignes 1062-1068

**Problème:**
La variable `now_for_alert` est utilisée sans avoir été initialisée dans certaines conditions de timezone.

**Impact:**
💥 Crash du bot avec `NameError` lors de la vérification des alertes d'inactivité.

**Solution:**
```python
# ✅ Initialiser la variable avant le bloc conditionnel:
now_for_alert = now  # Initialiser d'abord
if last_alert_dt.tzinfo is not None and now.tzinfo is None:
    last_alert_dt = last_alert_dt.replace(tzinfo=None)
```

---

### 3. **PERFORMANCE CRITIQUE: Opérations Google Sheets bloquantes**

**Fichier:** `cogs/scene_surveillance.py` - Multiple emplacements

**Problème:**
Les appels directs à l'API Google Sheets (lignes 131, 146, 198, 261, 272, 315, 328, 344, 742, etc.) ne sont PAS enveloppés dans `asyncio.to_thread()`, ce qui bloque la boucle d'événements.

**Impact:**
🐌 Bot non-responsive pendant les opérations Google Sheets, timeouts et déconnexions possibles.

**Solution:**
```python
# ❌ AVANT:
self.gc = gspread.authorize(self.credentials)
worksheet = sheet.worksheet("Sheet1")

# ✅ APRÈS:
self.gc = await asyncio.to_thread(gspread.authorize, self.credentials)
worksheet = await asyncio.to_thread(sheet.worksheet, "Sheet1")
```

**Fichiers à corriger:**
- `cogs/scene_surveillance.py` (priorité haute - nombreuses opérations)
- Vérifier tous les autres cogs utilisant Google Sheets

---

## 🟠 ÉLEVÉ - À corriger rapidement

### 4. **Import manquant**

**Fichier:** `cogs/scene_surveillance.py`

**Problème:**
Utilise `logger` partout mais n'importe pas le module `logging` (seulement `logging.basicConfig` à la ligne 21).

**Impact:**
`NameError` possible si logging n'est pas initialisé ailleurs.

**Solution:**
```python
import logging
```

---

### 5. **Import en double**

**Fichier:** `cogs/RPTracker.py` - Lignes 6 et 9

**Problème:**
`asyncio` importé deux fois.

**Impact:**
Code smell, indication de maintenance négligée.

**Solution:**
Supprimer l'import dupliqué.

---

### 6. **Méthode définie deux fois**

**Fichier:** `cogs/bump.py` - Lignes 455-462 et 484-485

**Problème:**
La méthode `cog_unload()` est définie deux fois. La seconde définition écrase la première.

**Impact:**
La première implémentation (avec gestion d'erreur appropriée) n'est jamais exécutée.

**Solution:**
Supprimer la définition dupliquée aux lignes 484-485.

---

### 7. **Utilisation non sécurisée de thread avec event loop**

**Fichier:** `main.py` - Lignes 242-244

**Problème:**
Utilisation de `asyncio.run_coroutine_threadsafe()` dans un thread daemon sans gestion d'erreur ou validation de l'event loop.

**Impact:**
Race conditions ou erreurs d'event loop possibles pendant l'arrêt.

**Solution:**
```python
try:
    if self.bot and self.bot.loop and not self.bot.loop.is_closed():
        asyncio.run_coroutine_threadsafe(
            self.bot.change_presence(), self.bot.loop
        )
except Exception as e:
    logger.debug(f"⚠️ Heartbeat failed: {e}")
```

---

### 8. **Import de module incompatible**

**Fichier:** `monitoring_minimal.py` - Ligne 5

**Problème:**
Importe `get_last_heartbeat, get_request_count` depuis le module `server` mais ces fonctions n'existent pas dans `server_minimal.py` et ne sont jamais utilisées.

**Impact:**
Erreur d'import si `server.py` n'existe pas ou manque ces fonctions.

**Solution:**
Supprimer les imports inutilisés ou corriger le chemin d'import.

---

### 9. **Risque de fuite mémoire: Pas de nettoyage de cache**

**Fichier:** `cogs/cards/storage.py`

**Problème:**
Les caches ne sont jamais vidés, seulement rafraîchis. Avec un TTL de 5 secondes et plusieurs caches, cela peut accumuler de la mémoire.

**Impact:**
Utilisation mémoire croissante sans limite dans les instances long-running.

**Solution:**
```python
# Ajouter une limite de taille de cache et un mécanisme de nettoyage
from collections import OrderedDict

class LRUCache(OrderedDict):
    def __init__(self, max_size=1000):
        super().__init__()
        self.max_size = max_size

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        if len(self) > self.max_size:
            self.popitem(last=False)
```

---

## 🟡 MOYEN - À planifier

### 10. **Dépendance dépréciée**

**Fichier:** `requirements.txt` - Ligne 9

**Problème:**
Le package `oauth2client` est officiellement déprécié et non maintenu depuis 2017.

**Impact:**
Vulnérabilités de sécurité, incompatibilité avec les nouvelles versions de Python.

**Solution:**
Supprimer `oauth2client` et utiliser exclusivement `google-auth`.

---

### 11. **TTL de cache trop agressif**

**Fichier:** `cogs/cards/config.py` - Ligne 31

**Problème:**
`CACHE_VALIDITY_DURATION = 5` (secondes) est extrêmement agressif pour des données Google Sheets.

**Impact:**
⚠️ Risque élevé d'atteindre les limites de taux de l'API Google Sheets (300 requêtes/minute/utilisateur).

**Solution:**
```python
# Augmenter à au moins 60 secondes
CACHE_VALIDITY_DURATION = 60
```

---

### 12. **Pas de protection contre le rate limiting**

**Fichier:** `cogs/scene_surveillance.py`

**Problème:**
Plusieurs opérations Google Sheets (batch updates, reads) sans logique de rate limiting ou backoff.

**Impact:**
Épuisement du quota API, erreurs 429 causant des échecs de fonctionnalités.

**Solution:**
Implémenter un backoff exponentiel et une file d'attente de requêtes.

---

### 13. **Opération longue sans points de contrôle**

**Fichier:** `cogs/InactiveUserTracker.py` - Lignes 199-220

**Problème:**
`history(limit=None, after=cutoff_date)` peut traiter des millions de messages sans sauvegardes intermédiaires.

**Impact:**
Si interrompu, toute la progression est perdue. Peut causer des problèmes de mémoire avec de gros historiques.

**Solution:**
Ajouter des sauvegardes de checkpoint tous les N messages.

---

### 14. **Démarrage de tâche avant fin d'initialisation**

**Fichier:** `cogs/scene_surveillance.py` - Lignes 171-172

**Problème:**
Les tâches `activity_monitor` et `inactivity_checker` démarrent dans `__init__` avant de vérifier que Google Sheets est disponible.

**Impact:**
Les tâches s'exécutent avec un état incomplet, causant des erreurs difficiles à débuguer.

**Solution:**
Démarrer les tâches seulement après vérification de l'initialisation réussie.

---

### 15. **Pas de nettoyage de ressources avant redémarrage**

**Fichier:** `main.py` - Lignes 265-268

**Problème:**
Nettoyage mémoire avec `gc.collect()` mais pas de nettoyage des threads, connexions ouvertes, ou ressources bot.

**Impact:**
Fuites de ressources accumulées entre les tentatives de redémarrage.

**Solution:**
```python
# Ajouter un nettoyage approprié
if self.bot and not self.bot.is_closed():
    await self.bot.close()
# Nettoyer les threads
# Fermer les sessions HTTP
gc.collect()
```

---

### 16. **Contenu inapproprié dans message utilisateur**

**Fichier:** `cogs/bump.py` - Ligne 406

**Problème:**
Message contenant un langage grossier: "Bump le serveur enculé"

**Impact:**
Non professionnel, potentiellement offensant pour les utilisateurs.

**Solution:**
```python
# Remplacer par un langage approprié
"⚠️ Ça fait 24h ! N'oubliez pas de bump le serveur"
```

---

### 17. **IDs Discord en dur**

**Fichiers:** Plusieurs fichiers à travers le codebase

**Problème:**
IDs Discord codés en dur partout (ex: `self.mj_role_id = 1018179623886000278`).

**Impact:**
Difficile à déployer sur différents serveurs, pas de configuration basée sur l'environnement.

**Solution:**
Déplacer tous les IDs vers des variables d'environnement ou un fichier de config.

---

### 18. **Récupération d'erreur faible dans RPTracker**

**Fichier:** `cogs/RPTracker.py` - Lignes 70-95

**Problème:**
Le gestionnaire d'erreur essaie de redémarrer la tâche mais n'a pas de limite de tentatives maximum.

**Impact:**
Boucles infinies de redémarrage sur erreurs persistantes, logging excessif.

**Solution:**
Ajouter un compteur de tentatives maximum et un backoff exponentiel.

---

### 19. **Pas de validation d'entrée dans les commandes Discord**

**Fichier:** `cogs/InactiveUserTracker.py` - Ligne 25

**Problème:**
Les paramètres `max_days` et `limit_days` ne sont pas validés pour les valeurs négatives ou extrêmes.

**Impact:**
Crashes potentiels ou épuisement de ressources avec des entrées malveillantes.

**Solution:**
```python
@app_commands.command(name="check_inactive")
async def check_inactive_users(
    self,
    interaction: discord.Interaction,
    max_days: int = 30,
    limit_days: int = 7
):
    # Validation
    if max_days < 1 or max_days > 365:
        await interaction.response.send_message(
            "❌ max_days doit être entre 1 et 365",
            ephemeral=True
        )
        return
    # ...
```

---

## 🔵 FAIBLE - Améliorations qualité

### 20. **Duplication de code**

**Fichiers:** Plusieurs cogs

**Problème:**
Patterns de gestion d'erreur similaires répétés à travers les cogs (try-except-log-traceback).

**Impact:**
Fardeau de maintenance, améliorations de gestion d'erreur inconsistantes.

**Solution:**
Créer des décorateurs ou utilitaires partagés de gestion d'erreur.

---

### 21. **Absence de type hints**

**Fichiers:** À travers tout le codebase

**Problème:**
Beaucoup de fonctions manquent d'annotations de type (ex: `def setup_google_sheets(self):`).

**Impact:**
Support IDE réduit, plus difficile de catcher les bugs liés aux types.

**Solution:**
Ajouter des type hints à toutes les signatures de fonction.

---

### 22. **Format de logging inconsistant**

**Fichiers:** Plusieurs fichiers

**Problème:**
Mélange de logging basé sur emojis (`logger.info("✅ Success")`) et texte simple.

**Impact:**
Parsing de logs inconsistant, plus difficile d'automatiser l'analyse des logs.

**Solution:**
Standardiser sur un format ou utiliser structured logging.

---

### 23. **Magic numbers**

**Fichiers:** À travers le codebase

**Problème:**
Nombres non expliqués comme `timeout=10.0`, `limit=100`, `sleep(2)`.

**Impact:**
Peu clair pourquoi des valeurs spécifiques ont été choisies, difficile de régler les performances.

**Solution:**
Extraire vers des constantes nommées avec commentaires explicatifs.

---

### 24. **Docstrings manquantes**

**Fichiers:** Plusieurs fichiers

**Problème:**
Beaucoup de méthodes publiques manquent de docstrings expliquant les paramètres et le comportement.

**Impact:**
Plus difficile pour les nouveaux développeurs de comprendre le code, support IDE réduit.

**Solution:**
Ajouter des docstrings complètes à toutes les méthodes publiques.

---

### 25. **Mélange de langues dans le code**

**Fichiers:** À travers le codebase

**Problème:**
Mélange de français et anglais dans les noms de variables, commentaires et messages.

**Impact:**
Confusant pour les contributeurs internationaux, style de code inconsistant.

**Solution:**
Standardiser sur l'anglais pour le code, français pour les messages utilisateur.

---

### 26. **Gestionnaires d'exception vides**

**Fichier:** `cogs/scene_surveillance.py` - Lignes 67-68, 156-157

**Problème:**
Blocs `except: pass` avalent les erreurs silencieusement.

**Impact:**
Bugs cachés, débogage difficile quand les choses échouent silencieusement.

**Solution:**
```python
# Au minimum logger l'exception
except Exception as e:
    logger.debug(f"Error: {e}")
```

---

### 27. **Préoccupations de thread safety**

**Fichier:** `cogs/cards/storage.py`

**Problème:**
Utilise `threading.RLock()` mais certaines opérations accèdent au cache en dehors du contexte de verrouillage.

**Impact:**
Race conditions potentielles dans des scénarios haute concurrence.

**Solution:**
Auditer tous les points d'accès au cache pour une utilisation appropriée du verrou.

---

### 28. **Pas de health check pour Google Sheets**

**Fichiers:** Plusieurs cogs

**Problème:**
Pas de vérifications de santé proactives pour la disponibilité de l'API Google Sheets.

**Impact:**
Les opérations échouent silencieusement jusqu'à l'interaction utilisateur, pas d'alerte.

**Solution:**
Ajouter des health checks périodiques avec alerte vers un canal admin.

---

### 29. **Pas de mécanisme de retry avec backoff**

**Fichiers:** Tous les cogs utilisant Google Sheets

**Problème:**
Aucun mécanisme de retry automatique avec backoff exponentiel pour les erreurs temporaires d'API.

**Impact:**
Échecs sur erreurs transitoires qui auraient pu réussir avec un retry.

**Solution:**
```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10)
)
async def safe_sheets_operation():
    # opération Google Sheets
    pass
```

---

## 📊 Statistiques Résumées

| Sévérité | Nombre | Pourcentage |
|----------|--------|-------------|
| 🔴 Critique | 3 | 10% |
| 🟠 Élevé | 6 | 21% |
| 🟡 Moyen | 10 | 34% |
| 🔵 Faible | 10 | 34% |
| **Total** | **29** | **100%** |

### Catégories de problèmes:
- **Sécurité**: 1 (Critique)
- **Bugs**: 5 (1 Critique, 4 Élevés)
- **Performance**: 5 (1 Critique, 4 Moyens)
- **Maintenance**: 8 (2 Élevés, 4 Moyens, 2 Faibles)
- **Qualité de Code**: 8 (Faibles)
- **Documentation**: 2 (Faibles)

---

## 🎯 Recommandations Prioritaires

### Priorité IMMÉDIATE (Cette semaine):
1. ✅ **Sécurité**: Remplacer tous les `eval()` par `json.loads()` (#1)
2. ✅ **Bug**: Corriger la variable `now_for_alert` non définie (#2)
3. ✅ **Performance**: Envelopper les opérations Google Sheets dans `asyncio.to_thread()` (#3)

### Priorité URGENTE (Ce mois):
4. 🔧 Augmenter le TTL du cache à 60 secondes (#11)
5. 🔧 Remplacer `oauth2client` déprécié (#10)
6. 🔧 Corriger les imports manquants/dupliqués (#4, #5, #6, #8)

### Priorité MOYENNE (Prochains mois):
7. 📝 Ajouter rate limiting et backoff pour Google Sheets (#12, #29)
8. 📝 Implémenter nettoyage de cache et limites de taille (#9)
9. 📝 Déplacer les IDs Discord vers config/env (#17)
10. 📝 Ajouter validation d'entrée utilisateur (#19)

### Améliorations Continues:
- Ajouter type hints progressivement (#21)
- Documenter avec docstrings (#24)
- Standardiser le logging (#22)
- Extraire les magic numbers (#23)

---

**Note**: Ce TODO ne modifie aucune fonctionnalité existante. Toutes les corrections proposées maintiennent la compatibilité avec Google Sheets et Render.
