import datetime
import pytest
from unittest.mock import AsyncMock
import sys, pathlib

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))
from cogs import InactiveUserTracker as iut

# Patch discord Color for tests
class DummyColor:
    blue = staticmethod(lambda: None)
    gold = staticmethod(lambda: None)
    green = staticmethod(lambda: None)
    orange = staticmethod(lambda: None)
    red = staticmethod(lambda: None)

iut.discord.Color = DummyColor

class DummyThread:
    def __init__(self, id, name, parent=None):
        self.id = id
        self.name = name
        self.parent = parent

iut.discord.Thread = DummyThread

class DummyTextChannel:
    def __init__(self, id, name, threads=None):
        self.id = id
        self.name = name
        self._threads = threads or []
    async def active_threads(self):
        return self._threads
    async def archived_threads(self, limit=100, private=True):
        return []

class DummyCategory:
    def __init__(self, id, name, channels):
        self.id = id
        self.name = name
        self.channels = channels

iut.discord.TextChannel = DummyTextChannel

iut.discord.CategoryChannel = DummyCategory

iut.discord.ForumChannel = DummyTextChannel

iut.discord.errors = type('errors', (), {'Forbidden': Exception})

class DummyGuild:
    def __init__(self, channels, active_threads=None):
        self._channels = {c.id: c for c in channels}
        self.active_threads = active_threads or []
        self.me = object()
    def get_channel(self, cid):
        return self._channels.get(cid)

class DummyCtx:
    def __init__(self, guild):
        self.guild = guild

@pytest.mark.asyncio
async def test_get_channels_to_check():
    tracker = iut.InactiveUserTracker(bot=None)
    tracker._update_status = AsyncMock()
    thread = DummyThread(3, 'thread')
    text_channel = DummyTextChannel(2, 'text', threads=[thread])
    priority = DummyTextChannel(tracker.priority_channel_id, 'priority')
    category = DummyCategory(tracker.category_ids[0], 'cat', [text_channel])
    guild = DummyGuild([priority, category])
    ctx = DummyCtx(guild)
    channels = await tracker._get_channels_to_check(ctx, None)
    assert priority in channels
    assert text_channel in channels
    assert thread in channels

class DummyMessage:
    def __init__(self, author_id, created_at):
        self.author = type('A', (), {'id': author_id})
        self.created_at = created_at

class HistoryChannel(DummyTextChannel):
    def __init__(self, id, name, messages):
        super().__init__(id, name)
        self.messages = messages
    def permissions_for(self, me):
        return type('P', (), {'read_message_history': True})
    async def history(self, limit=None, after=None):
        for m in self.messages:
            if after is None or m.created_at > after:
                yield m

@pytest.mark.asyncio
async def test_analyze_messages():
    tracker = iut.InactiveUserTracker(bot=None)
    tracker._update_status = AsyncMock()
    now = datetime.datetime.now(datetime.timezone.utc)
    msg = DummyMessage(1, now - datetime.timedelta(days=1))
    channel = HistoryChannel(10, 'chan', [msg])
    ctx = DummyCtx(type('G', (), {'me': object()}))
    result = await tracker._analyze_messages(ctx, [channel], [type('M', (), {'id':1})], None, now - datetime.timedelta(days=30))
    last_dates, channels_processed, messages_checked, total_channels, start_time = result
    assert last_dates[1] == msg.created_at
    assert channels_processed == 1
    assert messages_checked == 1
    assert total_channels == 1

class DummyMember:
    def __init__(self, id, mention, display_name, avatar=None, joined_at=None):
        self.id = id
        self.mention = mention
        self.display_name = display_name
        self.avatar = avatar
        self.joined_at = joined_at

@pytest.mark.asyncio
async def test_generate_report():
    tracker = iut.InactiveUserTracker(bot=None)
    tracker._update_status = AsyncMock()
    iut.discord.Embed = type('Embed', (), {'__init__': lambda self, **kwargs: None, 'set_thumbnail': lambda self, url: None, 'add_field': lambda self, name, value, inline=True: None})
    ctx = type('C', (), {'send': AsyncMock()})
    role = type('R', (), {'name': 'role'})
    tz_now = datetime.datetime.now(datetime.timezone.utc)
    start_time = datetime.datetime.now() - datetime.timedelta(minutes=1)
    member1 = DummyMember(1, '@1', 'm1')
    member2 = DummyMember(2, '@2', 'm2')
    last_dates = {1: tz_now - datetime.timedelta(days=5)}
    await tracker._generate_report(ctx, role, [member1, member2], last_dates, None, start_time, 3, 30, 0, 0, 0)
    assert ctx.send.await_count == 2
