import pytest

from cogs.cards.logging import CardsLoggingManager


class DummySheet:
    def __init__(self):
        self.rows = []

    def append_row(self, row):
        self.rows.append(row)


class DummyStorage:
    def __init__(self):
        self.sheet_logs = DummySheet()


def test_log_trade_direct_multiple_cards():
    storage = DummyStorage()
    manager = CardsLoggingManager(storage)

    result = manager.log_trade_direct(
        offerer_id=1,
        offerer_name="User1",
        target_id=2,
        target_name="User2",
        offer_cards=[("CatA", "CardA"), ("CatB", "CardB")],
        return_cards=[("CatC", "CardC"), ("CatD", "CardD")],
        source="test",
    )

    assert result
    assert len(storage.sheet_logs.rows) == 8
