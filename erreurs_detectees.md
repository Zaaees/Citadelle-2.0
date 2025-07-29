# Liste des erreurs et points à corriger détectés dans le code

## 1. Utilisation risquée de `eval` pour les credentials Google
- **Fichier : `cogs/RPTracker.py`**
- Ligne : `self.credentials = service_account.Credentials.from_service_account_info(eval(os.getenv('SERVICE_ACCOUNT_JSON')), ...)`
- **Problème :** Utiliser `eval` sur des variables d'environnement est dangereux (faille de sécurité potentielle). Préférer `json.loads`.

## 2. Gestion d'erreur : impression console au lieu de log
- **Fichiers concernés :**
    - `cogs/RPTracker.py` (plusieurs `print` dans les exceptions)
    - `cogs/ticket.py` (plusieurs `print` dans les exceptions)
- **Problème :** Utiliser `logging.error` ou `logger.error` au lieu de `print` pour une meilleure traçabilité.

## 4. Vérification des variables d'environnement
- **Fichiers concernés :**
    - `cogs/Cards.py` (init)
    - `cleanup_old_reminders.py`
- **Problème :** Les variables d'environnement sont vérifiées mais le script peut continuer sans elles. Ajouter une levée d'exception ou un arrêt clair si une variable critique manque.

## 5. Gestion des exceptions Google Sheets
- **Fichier : `cogs/bump.py`**
- Méthode : `load_last_bump`
- **Problème :** Les erreurs de l'API Google Sheets sont logguées, mais un échec répété lève une RuntimeError sans notification utilisateur. Ajouter une notification Discord ou un log critique.

## 6. Utilisation de `asyncio.sleep` dans les gestionnaires d'erreur
- **Fichier : `cogs/RPTracker.py`**
- **Problème :** Bien que courant pour éviter les boucles d'erreur, cela peut masquer un problème persistant. Prévoir une alerte si trop d'erreurs consécutives.

## 7. Sécurité sur les opérations du Vault
- **Fichier : `cogs/cards/vault.py`**
- **Problème :** Les logs de sécurité sont présents, mais il serait utile d'ajouter une notification admin en cas de tentative suspecte (ex : dépôt de carte "Full").

## 8. Divers
- **Certains scripts utilisent des valeurs d'identifiants Discord, Google Sheets ou autres en "dur".**
  - Préférer l'utilisation de variables d'environnement ou d'un fichier de configuration centralisé.
- **Beaucoup de gestion d'exceptions se limite à un simple log ou print.**
  - Pour les tâches critiques, prévoir une notification Discord ou un suivi plus poussé.

---

> **Note :** Cette liste ne prétend pas être exhaustive, mais regroupe les erreurs et points d'amélioration détectés lors de l'analyse automatique. Un audit manuel plus poussé est recommandé pour valider la sécurité et la robustesse globale du projet.
