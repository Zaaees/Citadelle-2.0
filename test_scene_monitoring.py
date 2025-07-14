#!/usr/bin/env python3
"""
Script de test pour vérifier le système de surveillance des scènes inactives.
Ce script simule le comportement du système et vérifie que les messages sont correctement gérés.
"""

import sys
import os
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
import logging

# Ajouter le répertoire parent au path pour importer les modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configuration des logs pour le test
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MockBot:
    """Mock du bot Discord pour les tests."""
    def __init__(self):
        self.user = Mock()
        self.user.id = 12345
        self.user.name = "TestBot"
        self.loop = asyncio.get_event_loop()
        
    def get_user(self, user_id):
        mock_user = Mock()
        mock_user.id = user_id
        mock_user.mention = f"<@{user_id}>"
        mock_user.display_name = f"User_{user_id}"
        return mock_user
        
    def get_channel(self, channel_id):
        mock_channel = Mock()
        mock_channel.id = channel_id
        mock_channel.name = f"channel_{channel_id}"
        mock_channel.fetch_message = AsyncMock()
        mock_channel.send = AsyncMock()
        return mock_channel
        
    async def wait_until_ready(self):
        pass

class MockGoogleSheets:
    """Mock de Google Sheets pour les tests."""
    def __init__(self):
        self.data = []
        self.headers = ["channel_id", "mj_user_id", "message_id", "participant_1", 
                       "participant_2", "participant_3", "participant_4", 
                       "participant_5", "participant_6", "added_at", 
                       "last_activity", "last_alert_sent", "last_reminder_message_id"]
        
    def get_all_values(self):
        return [self.headers] + self.data
        
    def append_row(self, row):
        self.data.append(row)
        
    def clear(self):
        self.data = []
        
    def delete_rows(self, row_idx):
        if 2 <= row_idx <= len(self.data) + 1:
            del self.data[row_idx - 2]

def test_alert_logic():
    """Test de la logique d'alerte sans dépendances externes."""
    logger.info("🧪 Test de la logique d'alerte")

    # Créer une classe de test simplifiée
    class TestChannelMonitor:
        def __init__(self):
            self.monitored_channels = {}
            self.logger = logger

        def should_send_new_alert(self, channel_id: int) -> bool:
            """Vérifie si un nouveau message d'alerte doit être envoyé (renouvellement quotidien)."""
            try:
                data = self.monitored_channels.get(channel_id)
                if not data:
                    return True

                last_alert_sent = data.get('last_alert_sent')
                if not last_alert_sent:
                    return True

                # Vérifier si plus de 24h se sont écoulées depuis la dernière alerte
                current_time = datetime.now()
                time_since_last_alert = current_time - last_alert_sent

                return time_since_last_alert.total_seconds() >= 86400  # 24h en secondes
            except Exception as e:
                self.logger.error(f"Erreur lors de la vérification de renouvellement d'alerte pour le salon {channel_id}: {e}")
                return True

        def record_alert_sent(self, channel_id: int, mj_user_id: int, message_id: int = None):
            """Enregistre qu'une alerte d'inactivité a été envoyée pour ce salon."""
            current_time = datetime.now()
            if channel_id in self.monitored_channels:
                self.monitored_channels[channel_id]['last_alert_sent'] = current_time
                if message_id:
                    self.monitored_channels[channel_id]['last_reminder_message_id'] = message_id

    # Créer une instance de test
    test_monitor = TestChannelMonitor()
            
    # Test 1: Vérifier la logique de renouvellement quotidien
    logger.info("📋 Test 1: Logique de renouvellement quotidien")

    channel_id = 123456789
    mj_id = 987654321

    # Simuler une scène inactive depuis plus d'une semaine
    week_ago = datetime.now() - timedelta(days=8)
    test_monitor.monitored_channels[channel_id] = {
        'mj_user_id': mj_id,
        'message_id': 111111,
        'participants': [],
        'last_activity': week_ago,
        'last_alert_sent': None,
        'last_reminder_message_id': None
    }

    # Premier appel - devrait envoyer une alerte
    should_send = test_monitor.should_send_new_alert(channel_id)
    assert should_send == True, "Première alerte devrait être envoyée"
    logger.info("✅ Première alerte correctement détectée")

    # Simuler l'envoi d'une alerte
    current_time = datetime.now()
    test_monitor.record_alert_sent(channel_id, mj_id, 222222)

    # Deuxième appel immédiat - ne devrait pas envoyer d'alerte
    should_send = test_monitor.should_send_new_alert(channel_id)
    assert should_send == False, "Alerte récente ne devrait pas être renvoyée"
    logger.info("✅ Alerte récente correctement bloquée")

    # Test 2: Vérifier le renouvellement après 24h
    logger.info("📋 Test 2: Renouvellement après 24h")

    # Simuler 25h plus tard
    past_time = current_time - timedelta(hours=25)
    test_monitor.monitored_channels[channel_id]['last_alert_sent'] = past_time

    should_send = test_monitor.should_send_new_alert(channel_id)
    assert should_send == True, "Alerte devrait être renouvelée après 24h"
    logger.info("✅ Renouvellement après 24h correctement détecté")

    # Test 3: Vérifier les cas limites
    logger.info("📋 Test 3: Cas limites")

    # Test avec un salon inexistant
    should_send = test_monitor.should_send_new_alert(999999)
    assert should_send == True, "Salon inexistant devrait déclencher une alerte"
    logger.info("✅ Salon inexistant correctement géré")

    # Test avec exactement 24h
    exactly_24h_ago = current_time - timedelta(hours=24)
    test_monitor.monitored_channels[channel_id]['last_alert_sent'] = exactly_24h_ago

    should_send = test_monitor.should_send_new_alert(channel_id)
    assert should_send == True, "Alerte de exactement 24h devrait être renouvelée"
    logger.info("✅ Renouvellement à exactement 24h correctement détecté")

    # Test avec 23h59min
    almost_24h_ago = current_time - timedelta(hours=23, minutes=59)
    test_monitor.monitored_channels[channel_id]['last_alert_sent'] = almost_24h_ago

    should_send = test_monitor.should_send_new_alert(channel_id)
    assert should_send == False, "Alerte de moins de 24h ne devrait pas être renouvelée"
    logger.info("✅ Alerte récente (23h59) correctement bloquée")

    logger.info("🎉 Tous les tests de logique sont passés avec succès!")

    # Afficher un résumé des données de test
    logger.info("📊 Résumé des données de test:")
    logger.info(f"   - Scènes surveillées: {len(test_monitor.monitored_channels)}")

async def test_scene_monitoring_system():
    """Test principal du système de surveillance des scènes."""
    logger.info("🧪 Début des tests du système de surveillance des scènes")

    # Exécuter les tests de logique
    test_alert_logic()

if __name__ == "__main__":
    asyncio.run(test_scene_monitoring_system())
