import threading
import pytest

from cogs.cards.trading import TradingManager


class FakeLoggingManager:
    def log_card_remove(self, **kwargs):
        return True

    def log_trade_direct(self, **kwargs):
        return True

    def log_card_add(self, **kwargs):
        return True


class FakeStorage:
    def __init__(self):
        self._cards_lock = threading.RLock()
        self._board_lock = threading.RLock()
        self.entries = []
        self.logging_manager = FakeLoggingManager()

    # CRUD minimal
    def create_exchange_entry(self, owner, cat, name, ts):
        entry_id = len(self.entries) + 1
        self.entries.append({
            "id": entry_id,
            "owner": owner,
            "cat": cat,
            "name": name,
            "timestamp": ts,
        })
        return entry_id

    def get_exchange_entries(self):
        return list(self.entries)

    def get_exchange_entry(self, entry_id):
        for e in self.entries:
            if e["id"] == entry_id:
                return e
        return None

    def delete_exchange_entry(self, entry_id):
        for i, e in enumerate(self.entries):
            if e["id"] == entry_id:
                self.entries.pop(i)
                return True
        return False


@pytest.fixture()
def trading_manager():
    storage = FakeStorage()
    tm = TradingManager(storage, vault_manager=None)

    inventories = {}

    def has_card(uid, cat, name):
        return inventories.get(uid, {}).get((cat, name), 0) > 0

    def add_card(uid, cat, name):
        inventories.setdefault(uid, {})[(cat, name)] = inventories.get(uid, {}).get((cat, name), 0) + 1
        return True

    def remove_card(uid, cat, name):
        if not has_card(uid, cat, name):
            return False
        inventories[uid][(cat, name)] -= 1
        if inventories[uid][(cat, name)] == 0:
            del inventories[uid][(cat, name)]
        return True

    tm._user_has_card = has_card
    tm._add_card_to_user = add_card
    tm._remove_card_from_user = remove_card

    return tm, inventories, storage


def test_deposit_to_board(trading_manager):
    tm, inv, storage = trading_manager
    inv[1] = {("Cat", "Card"): 1}
    assert tm.deposit_to_board(1, "Cat", "Card")
    assert storage.entries[0]["owner"] == 1
    assert not tm._user_has_card(1, "Cat", "Card")


def test_take_from_board(trading_manager):
    tm, inv, storage = trading_manager
    inv[1] = {("Cat", "Card"): 1}
    tm.deposit_to_board(1, "Cat", "Card")
    inv[2] = {("Cat", "Offer"): 1}
    info = tm.initiate_board_trade(2, 1, "Cat", "Offer")
    assert info is not None
    # Rien n'a changé avant confirmation
    assert tm._user_has_card(2, "Cat", "Offer")
    assert storage.get_exchange_entries() != []

    assert tm.take_from_board(2, 1, "Cat", "Offer")
    assert tm._user_has_card(2, "Cat", "Card")
    assert tm._user_has_card(1, "Cat", "Offer")
    assert storage.get_exchange_entries() == []


def test_concurrent_take(trading_manager):
    tm, inv, storage = trading_manager
    inv[1] = {("Cat", "Card"): 1}
    tm.deposit_to_board(1, "Cat", "Card")
    inv[2] = {("Cat", "OfferA"): 1}
    inv[3] = {("Cat", "OfferB"): 1}

    results = []

    # Pré-validation (simule l'envoi des demandes)
    assert tm.initiate_board_trade(2, 1, "Cat", "OfferA")
    assert tm.initiate_board_trade(3, 1, "Cat", "OfferB")

    def attempt(uid, name):
        res = tm.take_from_board(uid, 1, "Cat", name)
        results.append(res)

    t1 = threading.Thread(target=attempt, args=(2, "OfferA"))
    t2 = threading.Thread(target=attempt, args=(3, "OfferB"))
    t1.start(); t2.start(); t1.join(); t2.join()

    assert sum(1 for r in results if r) == 1
    assert storage.get_exchange_entries() == []


def test_withdraw_from_board(trading_manager):
    tm, inv, storage = trading_manager
    inv[1] = {("Cat", "Card"): 1}
    tm.deposit_to_board(1, "Cat", "Card")
    assert not tm._user_has_card(1, "Cat", "Card")
    assert tm.withdraw_from_board(1, 1)
    assert tm._user_has_card(1, "Cat", "Card")
    assert storage.get_exchange_entries() == []


def test_board_view_pagination(monkeypatch):
    import asyncio
    import discord
    from types import SimpleNamespace
    from cogs.cards.views.trade_views import ExchangeBoardView

    offers = [
        {"id": i + 1, "owner": 1, "cat": "Cat", "name": f"Card{i}.png"}
        for i in range(30)
    ]

    class DummyTM:
        def list_board_offers(self):
            return offers

    dummy_cog = SimpleNamespace(
        trading_manager=DummyTM(),
        bot=SimpleNamespace(get_user=lambda uid: None),
    )
    user = discord.Object(id=1)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        async def create():
            return ExchangeBoardView(dummy_cog, user, guild=None)
        view = loop.run_until_complete(create())
    finally:
        loop.close()
        asyncio.set_event_loop(None)

    assert len(view.pages) == 2
    assert len(view.offer_select.options) == 25


def test_board_view_shows_member_name(monkeypatch):
    import asyncio
    import discord
    from types import SimpleNamespace
    from cogs.cards.views.trade_views import ExchangeBoardView

    offers = [
        {"id": 1, "owner": 42, "cat": "Cat", "name": "Card.png"}
    ]

    class DummyTM:
        def list_board_offers(self):
            return offers

    class DummyMember:
        display_name = "Tester"

    class DummyGuild:
        def get_member(self, uid):
            return DummyMember() if uid == 42 else None

    dummy_cog = SimpleNamespace(
        trading_manager=DummyTM(),
        bot=SimpleNamespace(get_user=lambda uid: None),
    )
    user = discord.Object(id=1)
    guild = DummyGuild()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        async def create():
            return ExchangeBoardView(dummy_cog, user, guild)
        view = loop.run_until_complete(create())
    finally:
        loop.close()
        asyncio.set_event_loop(None)

    assert "Tester" in view.offer_select.options[0].description
