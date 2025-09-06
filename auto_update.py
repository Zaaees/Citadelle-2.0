#!/usr/bin/env python3
"""
Script d'automatisation pour les mises à jour GitHub
Permet de committer et pousser les changements automatiquement
"""

import subprocess
import sys
import os
from datetime import datetime
import logging

# Configuration des logs (sans emojis pour compatibilité Windows)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("auto_update.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('auto_update')

class GitAutoUpdater:
    """Gestionnaire automatique des mises à jour Git."""
    
    def __init__(self, repo_path="."):
        self.repo_path = repo_path
        
    def run_git_command(self, command):
        """Exécute une commande Git et retourne le résultat."""
        try:
            result = subprocess.run(
                command, 
                shell=True, 
                capture_output=True, 
                text=True, 
                cwd=self.repo_path
            )
            
            if result.returncode == 0:
                logger.info(f"[OK] Commande reussie: {command}")
                return result.stdout.strip(), True
            else:
                logger.error(f"[ERREUR] Erreur commande: {command}")
                logger.error(f"Erreur: {result.stderr}")
                return result.stderr.strip(), False
                
        except Exception as e:
            logger.error(f"[EXCEPTION] Exception lors de l'execution: {e}")
            return str(e), False
    
    def check_git_status(self):
        """Vérifie s'il y a des changements à committer."""
        output, success = self.run_git_command("git status --porcelain")
        if success:
            changes = output.strip()
            return len(changes) > 0, changes
        return False, ""
    
    def get_changed_files(self):
        """Récupère la liste des fichiers modifiés."""
        output, success = self.run_git_command("git diff --name-only")
        untracked, _ = self.run_git_command("git ls-files --others --exclude-standard")
        
        changed_files = []
        if success and output:
            changed_files.extend(output.split('\n'))
        if untracked:
            changed_files.extend(untracked.split('\n'))
            
        return [f for f in changed_files if f.strip()]
    
    def generate_commit_message(self, changed_files):
        """Génère un message de commit automatique basé sur les fichiers modifiés."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Analyser les types de changements
        categories = {
            'config': [],
            'core': [],
            'cogs': [],
            'monitoring': [],
            'docs': [],
            'other': []
        }
        
        for file in changed_files:
            if file.endswith('.md') or file.endswith('.txt'):
                categories['docs'].append(file)
            elif file.startswith('cogs/'):
                categories['cogs'].append(file)
            elif file in ['main.py', 'bot_state.py', 'server.py']:
                categories['core'].append(file)
            elif file in ['monitoring.py', 'render_keepalive.py', 'render_diagnostic.py']:
                categories['monitoring'].append(file)
            elif file.endswith('.json') or file.endswith('.yaml') or file.endswith('.yml'):
                categories['config'].append(file)
            else:
                categories['other'].append(file)
        
        # Construire le message
        if categories['monitoring']:
            commit_type = "fix(monitoring)"
            subject = "update monitoring and connection stability"
        elif categories['core']:
            commit_type = "feat(core)" if len(changed_files) > 2 else "fix(core)"
            subject = "update core bot functionality"
        elif categories['cogs']:
            commit_type = "feat(cogs)" if len(categories['cogs']) > 1 else "fix(cogs)"
            subject = f"update {', '.join(categories['cogs'][:2])}" + ("..." if len(categories['cogs']) > 2 else "")
        elif categories['config']:
            commit_type = "chore(config)"
            subject = "update configuration files"
        elif categories['docs']:
            commit_type = "docs"
            subject = "update documentation"
        else:
            commit_type = "chore"
            subject = "update various files"
        
        # Message complet
        message = f"{commit_type}: {subject}\n\n"
        message += f"Auto-update performed at {timestamp}\n"
        message += f"Modified files: {', '.join(changed_files[:5])}"
        if len(changed_files) > 5:
            message += f" and {len(changed_files) - 5} more"
        
        message += "\n\nGenerated with [Claude Code](https://claude.ai/code)\n"
        message += "Co-Authored-By: Claude <noreply@anthropic.com>"
        
        return message
    
    def auto_commit_and_push(self, custom_message=None):
        """Effectue un commit et push automatique."""
        logger.info("[DEBUT] Demarrage de l'auto-update...")
        
        # Vérifier s'il y a des changements
        has_changes, status_output = self.check_git_status()
        if not has_changes:
            logger.info("[INFO] Aucun changement detecte")
            return True
        
        logger.info(f"[CHANGES] Changements detectes:\n{status_output}")
        
        # Récupérer les fichiers modifiés
        changed_files = self.get_changed_files()
        logger.info(f"[FILES] Fichiers modifies: {changed_files}")
        
        # Ajouter tous les fichiers
        _, success = self.run_git_command("git add .")
        if not success:
            logger.error("[ERREUR] Echec de l'ajout des fichiers")
            return False
        
        # Générer ou utiliser le message de commit
        if custom_message:
            commit_message = custom_message
        else:
            commit_message = self.generate_commit_message(changed_files)
        
        logger.info(f"[COMMIT] Message de commit:\n{commit_message}")
        
        # Créer le commit
        commit_command = f'git commit -m "{commit_message}"'
        _, success = self.run_git_command(commit_command)
        if not success:
            logger.error("[ERREUR] Echec du commit")
            return False
        
        # Pousser vers GitHub
        _, success = self.run_git_command("git push origin main")
        if not success:
            logger.error("[ERREUR] Echec du push")
            return False
        
        logger.info("[SUCCESS] Auto-update termine avec succes!")
        return True

def main():
    """Point d'entrée principal."""
    updater = GitAutoUpdater()
    
    # Arguments en ligne de commande
    if len(sys.argv) > 1:
        if sys.argv[1] == "--check":
            has_changes, _ = updater.check_git_status()
            if has_changes:
                print("Changes detected")
                sys.exit(0)
            else:
                print("No changes")
                sys.exit(1)
        elif sys.argv[1] == "--message" and len(sys.argv) > 2:
            custom_message = " ".join(sys.argv[2:])
            success = updater.auto_commit_and_push(custom_message)
            sys.exit(0 if success else 1)
    
    # Auto-update normal
    success = updater.auto_commit_and_push()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()