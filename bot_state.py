"""
Module pour gérer l'état global du bot de manière centralisée.
Évite les imports circulaires entre main.py et server.py.
"""

import threading
from datetime import datetime

# État global du bot pour monitoring
bot_state = {
    'status': 'initializing',  # initializing, connecting, connected, disconnected, error
    'last_ready': None,
    'last_disconnect': None,
    'restart_count': 0,
    'error_count': 0,
    'latency': None,
    'uptime_start': datetime.now()
}
state_lock = threading.Lock()

def update_bot_state(status, **kwargs):
    """Mettre à jour l'état du bot de manière thread-safe."""
    with state_lock:
        bot_state['status'] = status
        for key, value in kwargs.items():
            if key in bot_state:
                bot_state[key] = value

def get_bot_state():
    """Récupérer l'état du bot de manière thread-safe."""
    with state_lock:
        return bot_state.copy()

def reset_bot_state():
    """Réinitialiser l'état du bot (pour redémarrage)."""
    with state_lock:
        bot_state.update({
            'status': 'initializing',
            'last_ready': None,
            'last_disconnect': None,
            'latency': None,
            'uptime_start': datetime.now()
        })
        # Garder restart_count et error_count pour les statistiques