"""
Module de notifications pour le systeme Bazaar.
Surveille les nouvelles demandes d'echange et envoie des DM Discord.
"""

import discord
import logging
import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional, List, Dict, Any

if TYPE_CHECKING:
    from ..Cards import Cards

logger = logging.getLogger("bazaar_notifier")

# URL du Bazaar sur le site
BAZAAR_URL = "https://citadelle-2.onrender.com/trade"


class BazaarNotifier:
    """
    Gere les notifications Discord pour les demandes d'echange du Bazaar.

    Fonctionnement:
    - Verifie periodiquement la sheet TradeRequests pour les nouvelles demandes
    - Envoie un DM aux destinataires des nouvelles demandes
    - Marque les demandes comme notifiees pour eviter les doublons
    """

    def __init__(self, cog: "Cards"):
        self.cog = cog
        self.bot = cog.bot
        self.storage = cog.storage
        self._last_check_time: Optional[datetime] = None
        self._notified_trade_ids: set = set()
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def _get_trade_requests_sheet(self):
        """Recupere la sheet des demandes d'echange."""
        try:
            return self.storage.spreadsheet.worksheet("TradeRequests")
        except Exception:
            return None

    def _parse_trade_requests(self) -> List[Dict[str, Any]]:
        """
        Lit les demandes d'echange depuis la sheet.
        Retourne les demandes en attente qui n'ont pas ete notifiees.
        """
        sheet = self._get_trade_requests_sheet()
        if not sheet:
            return []

        try:
            records = sheet.get_all_records()
        except Exception as e:
            logger.warning(f"Erreur lecture TradeRequests: {e}")
            return []

        pending_requests = []
        now = datetime.now(timezone.utc)

        for i, record in enumerate(records):
            # Ignorer les demandes deja traitees ou notifiees
            trade_id = record.get("id", "")
            if not trade_id or trade_id in self._notified_trade_ids:
                continue

            # Verifier le statut
            if record.get("status") != "pending":
                continue

            # Verifier si deja notifie (colonne 14 = notified_at)
            notified_at = record.get("notified_at", "")
            if notified_at:
                self._notified_trade_ids.add(trade_id)
                continue

            # Verifier l'expiration
            try:
                expires_at_str = record.get("expires_at", "")
                if expires_at_str:
                    expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
                    if expires_at.tzinfo is None:
                        expires_at = expires_at.replace(tzinfo=timezone.utc)
                    if expires_at < now:
                        continue  # Expiree
            except (ValueError, TypeError):
                pass

            pending_requests.append({
                "row_index": i + 2,  # +2 pour header et index 0-based
                "id": trade_id,
                "requester_id": str(record.get("requester_id", "")),
                "requester_name": record.get("requester_name", ""),
                "target_id": str(record.get("target_id", "")),
                "target_name": record.get("target_name", ""),
                "offered_category": record.get("offered_category", ""),
                "offered_name": record.get("offered_name", ""),
                "requested_category": record.get("requested_category", ""),
                "requested_name": record.get("requested_name", ""),
                "created_at": record.get("created_at", ""),
            })

        return pending_requests

    async def _send_trade_notification(self, request: Dict[str, Any]) -> bool:
        """
        Envoie une notification DM au destinataire d'une demande d'echange.

        Returns:
            True si la notification a ete envoyee avec succes
        """
        try:
            target_id = int(request["target_id"])
            user = self.bot.get_user(target_id)

            if not user:
                try:
                    user = await self.bot.fetch_user(target_id)
                except (discord.NotFound, discord.HTTPException):
                    logger.warning(f"Utilisateur {target_id} introuvable pour notification")
                    return False

            # Creer l'embed de notification
            embed = discord.Embed(
                title="🏪 Nouvelle demande d'echange !",
                description=(
                    f"**{request['requester_name']}** vous propose un echange !\n\n"
                    f"**Il propose :**\n"
                    f"🎴 {request['offered_name'].replace('.png', '')} ({request['offered_category']})\n\n"
                    f"**En echange de :**\n"
                    f"🎴 {request['requested_name'].replace('.png', '')} ({request['requested_category']})\n\n"
                    f"⏰ Cette demande expire dans 24h."
                ),
                color=0xF59E0B,  # Couleur or/accent
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(
                name="➡️ Repondre a la demande",
                value=f"[Ouvrir le Bazaar]({BAZAAR_URL})",
                inline=False
            )
            embed.set_footer(text="Systeme de cartes Citadelle")

            # Creer un bouton pour ouvrir le Bazaar
            view = discord.ui.View()
            view.add_item(discord.ui.Button(
                label="Ouvrir le Bazaar",
                url=BAZAAR_URL,
                style=discord.ButtonStyle.link,
                emoji="🏪"
            ))

            # Envoyer le DM
            try:
                await user.send(embed=embed, view=view)
                logger.info(f"Notification envoyee a {user.display_name} pour echange {request['id']}")
                return True
            except discord.Forbidden:
                logger.warning(f"DM bloques pour {user.display_name} ({target_id})")
                return True  # Marquer comme notifie meme si DM bloque
            except discord.HTTPException as e:
                logger.error(f"Erreur envoi DM: {e}")
                return False

        except Exception as e:
            logger.error(f"Erreur notification: {e}")
            return False

    def _mark_as_notified(self, request: Dict[str, Any]) -> bool:
        """Marque une demande comme notifiee dans la sheet."""
        sheet = self._get_trade_requests_sheet()
        if not sheet:
            return False

        try:
            row_index = request["row_index"]
            now = datetime.now(timezone.utc).isoformat()

            # Colonne 14 = notified_at
            sheet.update_cell(row_index, 14, now)
            self._notified_trade_ids.add(request["id"])
            return True
        except Exception as e:
            logger.error(f"Erreur marquage notification: {e}")
            return False

    async def check_and_notify(self):
        """
        Verifie les nouvelles demandes et envoie les notifications.
        Appelee periodiquement par la tache de fond.
        """
        try:
            # Recuperer les demandes en attente non notifiees
            pending = await asyncio.to_thread(self._parse_trade_requests)

            if not pending:
                return

            logger.info(f"Trouvees {len(pending)} demandes a notifier")

            for request in pending:
                # Envoyer la notification
                success = await self._send_trade_notification(request)

                if success:
                    # Marquer comme notifie
                    await asyncio.to_thread(self._mark_as_notified, request)

                # Petit delai entre les notifications
                await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Erreur check_and_notify: {e}")

    async def _notification_loop(self):
        """Boucle principale de verification des notifications."""
        await self.bot.wait_until_ready()
        logger.info("BazaarNotifier demarre")

        while self._running:
            try:
                await self.check_and_notify()
            except Exception as e:
                logger.error(f"Erreur boucle notification: {e}")

            # Verifier toutes les 60 secondes
            await asyncio.sleep(60)

    def start(self):
        """Demarre la tache de fond de notification."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._notification_loop())
        logger.info("Tache BazaarNotifier lancee")

    def stop(self):
        """Arrete la tache de fond."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("BazaarNotifier arrete")


class TradeExpirationChecker:
    """
    Verifie les demandes d'echange expirees et les marque comme telles.
    """

    def __init__(self, cog: "Cards"):
        self.cog = cog
        self.storage = cog.storage
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def _get_trade_requests_sheet(self):
        """Recupere la sheet des demandes d'echange."""
        try:
            return self.storage.spreadsheet.worksheet("TradeRequests")
        except Exception:
            return None

    def _check_and_expire_requests(self) -> int:
        """
        Verifie et marque les demandes expirees.

        Returns:
            Nombre de demandes expirees
        """
        sheet = self._get_trade_requests_sheet()
        if not sheet:
            return 0

        try:
            records = sheet.get_all_records()
        except Exception:
            return 0

        now = datetime.now(timezone.utc)
        expired_count = 0

        for i, record in enumerate(records):
            # Ignorer les demandes non-pending
            if record.get("status") != "pending":
                continue

            # Verifier l'expiration
            try:
                expires_at_str = record.get("expires_at", "")
                if not expires_at_str:
                    continue

                expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)

                if expires_at < now:
                    # Marquer comme expire
                    row_index = i + 2  # +2 pour header et index 0-based
                    sheet.update_cell(row_index, 10, "expired")  # Colonne status
                    sheet.update_cell(row_index, 13, now.isoformat())  # Colonne resolved_at
                    expired_count += 1
                    logger.info(f"Demande {record.get('id')} marquee comme expiree")

            except (ValueError, TypeError) as e:
                logger.warning(f"Erreur parsing date expiration: {e}")
                continue

        return expired_count

    async def _expiration_loop(self):
        """Boucle de verification des expirations."""
        await self.cog.bot.wait_until_ready()
        logger.info("TradeExpirationChecker demarre")

        while self._running:
            try:
                expired = await asyncio.to_thread(self._check_and_expire_requests)
                if expired > 0:
                    logger.info(f"{expired} demande(s) d'echange expiree(s)")
            except Exception as e:
                logger.error(f"Erreur verification expiration: {e}")

            # Verifier toutes les 5 minutes
            await asyncio.sleep(300)

    def start(self):
        """Demarre la tache de verification."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._expiration_loop())
        logger.info("Tache TradeExpirationChecker lancee")

    def stop(self):
        """Arrete la tache."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("TradeExpirationChecker arrete")
