import pytest
from unittest.mock import AsyncMock, MagicMock
import sys, pathlib

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))
from cogs import Surveillance_scene as ss


@pytest.mark.asyncio
async def test_update_surveillance_reconnects_and_updates():
    scene = ss.SurveillanceScene.__new__(ss.SurveillanceScene)
    scene.sheet = None

    def reconnect():
        scene.sheet = object()

    scene.setup_google_sheets = MagicMock(side_effect=reconnect)
    scene.refresh_monitored_scenes = AsyncMock()
    scene.update_all_scenes = AsyncMock()

    await scene.update_surveillance()

    scene.setup_google_sheets.assert_called_once()
    assert scene.refresh_monitored_scenes.await_count == 1
    assert scene.update_all_scenes.await_count == 1


@pytest.mark.asyncio
async def test_update_surveillance_logs_error_when_no_sheet(caplog):
    scene = ss.SurveillanceScene.__new__(ss.SurveillanceScene)
    scene.sheet = None
    scene.setup_google_sheets = MagicMock()  # no side effect, remains None
    scene.refresh_monitored_scenes = AsyncMock()
    scene.update_all_scenes = AsyncMock()

    with caplog.at_level("ERROR"):
        await scene.update_surveillance()

    assert scene.setup_google_sheets.call_count == 3
    scene.refresh_monitored_scenes.assert_not_called()
    scene.update_all_scenes.assert_not_called()
    assert "Échec de la reconnexion" in caplog.text


@pytest.mark.asyncio
async def test_get_channel_from_link_with_mention():
    scene = ss.SurveillanceScene.__new__(ss.SurveillanceScene)
    mock_channel = MagicMock()
    mock_channel.name = "test"
    mock_channel.id = 123
    scene.bot = MagicMock()
    scene.bot.get_channel.return_value = mock_channel
    scene.bot.guilds = []

    result = await scene.get_channel_from_link('<#123>')

    scene.bot.get_channel.assert_called_once_with(123)
    assert result == mock_channel


@pytest.mark.asyncio
async def test_get_channel_from_link_logs_error_on_invalid_format(caplog):
    scene = ss.SurveillanceScene.__new__(ss.SurveillanceScene)
    scene.bot = MagicMock()
    scene.bot.get_channel.return_value = None
    scene.bot.guilds = []

    with caplog.at_level("ERROR"):
        result = await scene.get_channel_from_link('invalid')

    assert result is None
    assert "Format de lien ou mention non reconnu" in caplog.text

