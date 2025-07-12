# Guide de Déploiement et Surveillance du Bot Discord

## Améliorations Apportées

### 🔧 Optimisations de Connexion Discord
- Configuration avancée du client Discord avec timeouts optimisés
- Gestion améliorée des événements de connexion/déconnexion
- Cache des messages et membres optimisé pour réduire l'utilisation mémoire

### 🔄 Gestion Robuste des Tâches
- Redémarrage automatique des tâches en cas d'échec
- Gestion d'erreurs avancée pour toutes les tâches en arrière-plan
- Surveillance continue de l'état des tâches

### 📊 Système de Surveillance Avancé
- Monitoring en temps réel des métriques (mémoire, latence, erreurs)
- Collecte automatique des statistiques de santé
- Rapports détaillés accessibles via HTTP

### 🗄️ Optimisation des Ressources
- Gestionnaire de connexions Google Sheets avec mise en cache
- Nettoyage automatique des ressources expirées
- Garbage collection périodique

## Endpoints de Surveillance

### `/health` - Santé Basique (JSON)
```json
{
  "status": "healthy",
  "uptime_seconds": 3600,
  "uptime_human": "1:00:00",
  "request_count": 150,
  "last_heartbeat": "2024-01-01T12:00:00",
  "avg_latency_5min": 0.125,
  "avg_memory_mb_5min": 245.6,
  "total_errors": 2,
  "task_failures_1h": 0
}
```

### `/health/detailed` - Rapport Détaillé (Texte)
Rapport complet avec toutes les métriques et statistiques.

### `/ping` - Test de Connectivité
Simple réponse "pong" pour vérifier que le serveur répond.

## Configuration UptimeRobot

### Surveillance Recommandée
1. **Monitor Principal** : `https://votre-app.onrender.com/health`
   - Intervalle : 5 minutes
   - Timeout : 30 secondes
   - Mots-clés à surveiller : "healthy"

2. **Monitor de Backup** : `https://votre-app.onrender.com/ping`
   - Intervalle : 2 minutes
   - Timeout : 15 secondes

### Alertes Recommandées
- Email/SMS si le bot est down pendant plus de 10 minutes
- Webhook Discord pour notifications en temps réel

## Variables d'Environnement Render

Assurez-vous que ces variables sont configurées :

```
DISCORD_TOKEN=votre_token_discord
SERVICE_ACCOUNT_JSON={"type":"service_account",...}
GOOGLE_SHEET_ID_VALIDATION=votre_sheet_id
RENDER_EXTERNAL_URL=https://votre-app.onrender.com
PORT=10000
```

## Surveillance des Logs

### Logs Importants à Surveiller
- `🤖 Connecté en tant que` - Connexion réussie
- `🔌 Déconnecté de Discord` - Déconnexion détectée
- `🔄 Reconnexion réussie` - Reconnexion automatique
- `❌ Erreur critique` - Erreurs nécessitant attention
- `⚠️ Latence élevée` - Problèmes de performance
- `💾 Utilisation mémoire critique` - Problèmes de mémoire

### Commandes de Debug (si accès SSH)
```bash
# Vérifier l'utilisation mémoire
ps aux | grep python

# Vérifier les connexions réseau
netstat -an | grep :10000

# Logs en temps réel (si disponible)
tail -f logs/bot.log
```

## Résolution des Problèmes Courants

### Bot se déconnecte fréquemment
1. Vérifier les logs pour des erreurs spécifiques
2. Contrôler l'utilisation mémoire via `/health`
3. Vérifier la latence Discord
4. Redémarrer le service si nécessaire

### Tâches en arrière-plan arrêtées
- Les tâches se redémarrent automatiquement
- Vérifier les logs pour les erreurs de tâches
- Le système de surveillance redémarre les tâches défaillantes

### Utilisation mémoire élevée
- Le garbage collection automatique est activé
- Surveillance continue avec alertes à 500MB et 800MB
- Nettoyage automatique des caches expirés

### Latence élevée
- Surveillance automatique avec alertes > 10s
- Redémarrage automatique si latence critique
- Vérification de la connexion réseau Render

## Maintenance Préventive

### Quotidienne
- Vérifier les métriques via `/health/detailed`
- Contrôler les logs d'erreurs
- Vérifier le statut UptimeRobot

### Hebdomadaire
- Analyser les tendances de performance
- Vérifier l'utilisation des ressources
- Nettoyer les logs anciens si nécessaire

### Mensuelle
- Réviser les alertes et seuils
- Mettre à jour les dépendances si nécessaire
- Optimiser les configurations selon l'usage

## Support et Debugging

En cas de problème persistant :

1. Consulter `/health/detailed` pour un diagnostic complet
2. Vérifier les logs Render pour les erreurs système
3. Contrôler les métriques UptimeRobot
4. Redémarrer le service Render si nécessaire

Le système est maintenant beaucoup plus robuste et devrait considérablement réduire les déconnexions intempestives.
