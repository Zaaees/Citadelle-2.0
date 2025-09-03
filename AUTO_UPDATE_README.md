# Auto-Update GitHub - Guide d'utilisation

Ce système automatise vos mises à jour GitHub depuis votre machine locale. Une fois poussé sur GitHub, Render déploie automatiquement les changements.

## Workflow simplifié
**Votre PC** → **GitHub** → **Render** (déploiement automatique)

## Fichiers créés

- `auto_update.py` - Script Python principal d'automatisation
- `update.bat` - Script Windows pour exécution en un clic
- `update.sh` - Script Unix/Linux/macOS pour exécution en un clic

## Utilisation

### Méthode recommandée : Scripts en un clic

#### Windows
Double-cliquez simplement sur `update.bat`

#### Linux/macOS
```bash
./update.sh
```

### Méthode avancée : Python direct
```bash
# Auto-update normal (message généré automatiquement)
python auto_update.py

# Avec message personnalisé
python auto_update.py --message "fix: correction du bug de connexion"

# Vérifier s'il y a des changements (sans committer)
python auto_update.py --check
```

## Fonctionnalités intelligentes

### Génération automatique de messages de commit
Le système analyse les fichiers modifiés et génère automatiquement :
- Type de commit approprié (`fix:`, `feat:`, `chore:`, etc.)
- Description basée sur les fichiers modifiés
- Horodatage automatique
- Attribution à Claude Code

### Détection de changements
- Détecte automatiquement les fichiers modifiés
- Ne fait rien s'il n'y a aucun changement
- Affiche un résumé des modifications

### Gestion d'erreurs robuste
- Vérification de l'état Git avant opération
- Messages d'erreur détaillés
- Logs complets dans `auto_update.log`

## Exemples de messages générés automatiquement

```
fix(monitoring): update monitoring and connection stability

Auto-update performed at 2024-09-03 21:45:32
Modified files: monitoring.py, main.py, render_keepalive.py

Generated with [Claude Code](https://claude.ai/code)
Co-Authored-By: Claude <noreply@anthropic.com>
```

```
feat(cogs): update cogs/validation.py, cogs/Cards.py

Auto-update performed at 2024-09-03 21:50:15
Modified files: cogs/validation.py, cogs/Cards.py

Generated with [Claude Code](https://claude.ai/code)
Co-Authored-By: Claude <noreply@anthropic.com>
```

## Configuration

Aucune configuration supplémentaire nécessaire ! Le système utilise :
- La configuration Git existante de votre repository
- Les credentials GitHub déjà configurés

## Cas d'usage recommandés

1. **Développement quotidien** : Double-clic sur `update.bat` pour synchroniser rapidement
2. **Fixes spécifiques** : `python auto_update.py --message "fix: correction du problème X"`
3. **Nouvelles fonctionnalités** : `python auto_update.py --message "feat: ajout de la fonction Y"`

## Notes importantes

- L'auto-update pousse directement sur la branche `main`
- Render détecte automatiquement les changements et redéploie le bot
- Vérifiez toujours vos changements avec `git status` avant l'auto-update
- Les logs détaillés sont disponibles dans `auto_update.log`

---

**Workflow complet :**
1. Vous modifiez votre code
2. Double-clic sur `update.bat` (Windows) ou `./update.sh` (Linux/Mac)
3. Le script commit et pousse vers GitHub automatiquement
4. Render détecte les changements et redéploie votre bot

*Synchronisation automatique en 3 secondes !*