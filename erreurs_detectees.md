# Liste des erreurs et points à corriger détectés dans le code

## 1. Utilisation risquée de `eval` pour les credentials Google
- **Fichier : `cogs/RPTracker.py`**
- Ligne : `self.credentials = service_account.Credentials.from_service_account_info(eval(os.getenv('SERVICE_ACCOUNT_JSON')), ...)`
- **Problème :** Utiliser `eval` sur des variables d'environnement est dangereux (faille de sécurité potentielle). Préférer `json.loads`.




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
