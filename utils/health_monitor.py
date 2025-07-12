"""
Système de surveillance avancé pour la santé du bot.
"""
import logging
import time
import threading
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import psutil
import gc

logger = logging.getLogger('health_monitor')

class HealthMetrics:
    """Collecteur de métriques de santé."""
    
    def __init__(self):
        self.start_time = time.time()
        self.metrics = {
            'connection_events': [],
            'error_counts': {},
            'task_failures': {},
            'memory_usage': [],
            'latency_history': [],
            'last_heartbeat': None
        }
        self._lock = threading.RLock()
    
    def record_connection_event(self, event_type: str):
        """Enregistre un événement de connexion."""
        with self._lock:
            self.metrics['connection_events'].append({
                'type': event_type,
                'timestamp': time.time()
            })
            # Garder seulement les 100 derniers événements
            if len(self.metrics['connection_events']) > 100:
                self.metrics['connection_events'] = self.metrics['connection_events'][-100:]
    
    def record_error(self, error_type: str):
        """Enregistre une erreur."""
        with self._lock:
            if error_type not in self.metrics['error_counts']:
                self.metrics['error_counts'][error_type] = 0
            self.metrics['error_counts'][error_type] += 1
    
    def record_task_failure(self, task_name: str):
        """Enregistre l'échec d'une tâche."""
        with self._lock:
            if task_name not in self.metrics['task_failures']:
                self.metrics['task_failures'][task_name] = []
            self.metrics['task_failures'][task_name].append(time.time())
            # Garder seulement les échecs des dernières 24h
            cutoff = time.time() - 86400
            self.metrics['task_failures'][task_name] = [
                t for t in self.metrics['task_failures'][task_name] if t > cutoff
            ]
    
    def record_memory_usage(self):
        """Enregistre l'utilisation mémoire actuelle."""
        try:
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            
            with self._lock:
                self.metrics['memory_usage'].append({
                    'timestamp': time.time(),
                    'memory_mb': memory_mb
                })
                # Garder seulement les 1000 dernières mesures
                if len(self.metrics['memory_usage']) > 1000:
                    self.metrics['memory_usage'] = self.metrics['memory_usage'][-1000:]
        except Exception as e:
            logger.error(f"Erreur lors de l'enregistrement de la mémoire: {e}")
    
    def record_latency(self, latency: float):
        """Enregistre la latence."""
        with self._lock:
            self.metrics['latency_history'].append({
                'timestamp': time.time(),
                'latency': latency
            })
            # Garder seulement les 1000 dernières mesures
            if len(self.metrics['latency_history']) > 1000:
                self.metrics['latency_history'] = self.metrics['latency_history'][-1000:]
    
    def update_heartbeat(self):
        """Met à jour le heartbeat."""
        with self._lock:
            self.metrics['last_heartbeat'] = time.time()
    
    def get_health_summary(self) -> Dict:
        """Obtient un résumé de la santé."""
        with self._lock:
            current_time = time.time()
            uptime = current_time - self.start_time
            
            # Calculer les statistiques de latence
            recent_latencies = [
                m['latency'] for m in self.metrics['latency_history']
                if current_time - m['timestamp'] < 300  # 5 dernières minutes
            ]
            avg_latency = sum(recent_latencies) / len(recent_latencies) if recent_latencies else 0
            
            # Calculer l'utilisation mémoire récente
            recent_memory = [
                m['memory_mb'] for m in self.metrics['memory_usage']
                if current_time - m['timestamp'] < 300  # 5 dernières minutes
            ]
            avg_memory = sum(recent_memory) / len(recent_memory) if recent_memory else 0
            
            # Compter les erreurs récentes
            recent_errors = sum(self.metrics['error_counts'].values())
            
            # Compter les échecs de tâches récents
            recent_task_failures = 0
            for failures in self.metrics['task_failures'].values():
                recent_task_failures += len([f for f in failures if current_time - f < 3600])  # 1h
            
            return {
                'uptime_seconds': uptime,
                'uptime_human': str(timedelta(seconds=int(uptime))),
                'avg_latency_5min': round(avg_latency, 3),
                'avg_memory_mb_5min': round(avg_memory, 1),
                'total_errors': recent_errors,
                'task_failures_1h': recent_task_failures,
                'last_heartbeat': self.metrics['last_heartbeat'],
                'connection_events_count': len(self.metrics['connection_events'])
            }

class AdvancedHealthMonitor:
    """Moniteur de santé avancé."""
    
    def __init__(self, bot):
        self.bot = bot
        self.metrics = HealthMetrics()
        self.logger = logging.getLogger('advanced_health_monitor')
        self._monitoring = False
        self._monitor_thread = None
    
    def start_monitoring(self):
        """Démarre la surveillance."""
        if self._monitoring:
            return
        
        self._monitoring = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        self.logger.info("🔍 Surveillance avancée démarrée")
    
    def stop_monitoring(self):
        """Arrête la surveillance."""
        self._monitoring = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        self.logger.info("🛑 Surveillance avancée arrêtée")
    
    def _monitor_loop(self):
        """Boucle principale de surveillance."""
        while self._monitoring:
            try:
                # Enregistrer les métriques
                self.metrics.record_memory_usage()
                
                if self.bot.is_ready():
                    self.metrics.record_latency(self.bot.latency)
                    self.metrics.update_heartbeat()
                
                # Forcer le garbage collection périodiquement
                if int(time.time()) % 300 == 0:  # Toutes les 5 minutes
                    collected = gc.collect()
                    if collected > 0:
                        self.logger.info(f"🧹 Garbage collection: {collected} objets collectés")
                
                # Vérifier les seuils critiques
                self._check_critical_thresholds()
                
                time.sleep(30)  # Vérification toutes les 30 secondes
                
            except Exception as e:
                self.logger.error(f"Erreur dans la boucle de surveillance: {e}")
                time.sleep(60)  # Attendre plus longtemps en cas d'erreur
    
    def _check_critical_thresholds(self):
        """Vérifie les seuils critiques."""
        try:
            # Vérifier l'utilisation mémoire
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            
            if memory_mb > 500:  # Plus de 500MB
                self.logger.warning(f"⚠️ Utilisation mémoire élevée: {memory_mb:.1f}MB")
                if memory_mb > 800:  # Plus de 800MB
                    self.logger.critical(f"❌ Utilisation mémoire critique: {memory_mb:.1f}MB")
                    # Forcer le garbage collection
                    collected = gc.collect()
                    self.logger.info(f"🧹 Garbage collection forcé: {collected} objets collectés")
            
            # Vérifier la latence
            if self.bot.is_ready() and self.bot.latency > 10.0:
                self.logger.warning(f"⚠️ Latence élevée: {self.bot.latency:.2f}s")
                self.metrics.record_error('high_latency')
            
        except Exception as e:
            self.logger.error(f"Erreur lors de la vérification des seuils: {e}")
    
    def get_health_report(self) -> str:
        """Génère un rapport de santé détaillé."""
        summary = self.metrics.get_health_summary()
        
        report = f"""
🤖 **Rapport de santé du bot**
⏱️ Uptime: {summary['uptime_human']}
🏓 Latence moyenne (5min): {summary['avg_latency_5min']}s
💾 Mémoire moyenne (5min): {summary['avg_memory_mb_5min']}MB
❌ Erreurs totales: {summary['total_errors']}
🔄 Échecs de tâches (1h): {summary['task_failures_1h']}
📡 Événements de connexion: {summary['connection_events_count']}
💓 Dernier heartbeat: {datetime.fromtimestamp(summary['last_heartbeat']).strftime('%H:%M:%S') if summary['last_heartbeat'] else 'N/A'}
        """.strip()
        
        return report

# Instance globale
health_monitor = None

def get_health_monitor(bot=None):
    """Obtient l'instance du moniteur de santé."""
    global health_monitor
    if health_monitor is None and bot is not None:
        health_monitor = AdvancedHealthMonitor(bot)
    return health_monitor
