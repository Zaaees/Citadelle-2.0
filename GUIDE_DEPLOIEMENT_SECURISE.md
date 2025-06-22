# 🚀 Guide de Déploiement Sécurisé - Système de Découverte

## ⚠️ IMPORTANT - À LIRE AVANT DÉPLOIEMENT

Le nouveau système de découverte des cartes a été conçu pour **ÉVITER** les migrations automatiques qui pourraient écraser vos données existantes.

## 📋 Procédure de Déploiement

### Étape 1: Redémarrage du Bot
```bash
# Redémarrer le bot normalement
# La feuille "Découvertes" sera créée automatiquement
# AUCUNE migration ne se fera automatiquement
```

### Étape 2: Vérification de la Feuille
1. Vérifiez que la feuille "Découvertes" a été créée dans votre Google Sheets
2. Elle doit contenir uniquement les en-têtes :
   - `Card_Category`
   - `Card_Name` 
   - `Discoverer_ID`
   - `Discoverer_Name`
   - `Discovery_Timestamp`
   - `Discovery_Index`

### Étape 3: Migration Manuelle (OBLIGATOIRE)
```
!migrer_decouvertes
```

**Cette commande :**
- ✅ Vérifie si la migration a déjà été effectuée
- ✅ Échoue si des données existent déjà (sécurité)
- ✅ Migre les découvertes depuis l'ancien système
- ✅ Préserve l'ordre de découverte original

### Étape 4: Vérification Post-Migration
```
!reconstruire_mur
```

Cette commande reconstruit le mur avec le nouveau système pour vérifier que tout fonctionne.

## 🔒 Sécurités Intégrées

### Protection contre les Migrations Accidentelles
- **Pas de migration automatique** au démarrage
- **Vérification préalable** : échec si déjà migrée
- **Messages d'avertissement** clairs

### Option Force (⚠️ DANGER ⚠️)
```
!migrer_decouvertes force
```

**ATTENTION :** Cette commande efface TOUTES les découvertes existantes !
- À utiliser uniquement en cas de problème grave
- Demande confirmation explicite
- Logs détaillés de l'opération

## 📊 Vérifications de Santé

### Après Migration
1. **Vérifier les logs** pour confirmer le succès
2. **Compter les découvertes** migrées
3. **Tester une nouvelle découverte** de carte
4. **Vérifier le mur** avec `!reconstruire_mur`

### Commandes de Diagnostic
```
!verifier_mur          # Vérifie la cohérence du mur
!reconstruire_mur      # Reconstruit depuis le nouveau système
```

## 🚨 En Cas de Problème

### Si la Migration Échoue
1. Vérifiez les logs pour l'erreur exacte
2. Vérifiez les permissions Google Sheets
3. Contactez l'administrateur si nécessaire

### Si Vous Devez Recommencer
```
!migrer_decouvertes force
```
⚠️ **ATTENTION** : Cela efface tout et recommence !

### Rollback (Si Nécessaire)
Si vous devez revenir à l'ancien système :
1. Supprimez la feuille "Découvertes"
2. Redéployez l'ancienne version du code
3. Les données principales ne sont pas affectées

## ✅ Checklist de Déploiement

- [ ] Bot redémarré
- [ ] Feuille "Découvertes" créée automatiquement
- [ ] Commande `!migrer_decouvertes` exécutée avec succès
- [ ] Logs vérifiés (pas d'erreurs)
- [ ] Test d'une nouvelle découverte
- [ ] Commande `!reconstruire_mur` testée
- [ ] Système fonctionnel

## 📞 Support

En cas de problème :
1. Vérifiez les logs du bot
2. Vérifiez les permissions Google Sheets
3. Consultez la documentation complète dans `DISCOVERY_SYSTEM_UPGRADE.md`

---

**Date :** 2024-06-21  
**Version :** 2.0 Sécurisée  
**Statut :** Prêt pour déploiement
