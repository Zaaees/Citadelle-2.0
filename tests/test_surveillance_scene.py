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

    scene.setup_google_sheets.assert_called_once()
    scene.refresh_monitored_scenes.assert_not_called()
    scene.update_all_scenes.assert_not_called()
    assert "Impossible de se reconnecter" in caplog.text

