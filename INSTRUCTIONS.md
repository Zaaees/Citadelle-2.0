# Instructions pour les agents

Ce document contient les instructions importantes à suivre lors des modifications du bot.

## Système de logs des cartes
Toute opération qui modifie l'inventaire des cartes (ajout/retrait/échange/tirage) doit être loggée via `self.storage.logging_manager`. Le système est déjà intégré dans les méthodes existantes `add_card_to_user()` et `remove_card_from_user()` - passer les paramètres `user_name` et `source` pour un logging correct.
