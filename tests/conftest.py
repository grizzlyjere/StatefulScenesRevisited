from pathlib import Path
import shutil

import pytest
from homeassistant.core import HomeAssistant
from homeassistant import loader
from homeassistant.config_entries import ConfigEntries
from homeassistant.helpers import entity_registry, device_registry, area_registry, label_registry


@pytest.fixture
async def hass(tmp_path):
    shutil.copytree(Path(__file__).parents[1] / "custom_components", tmp_path / "custom_components")
    instance = HomeAssistant(str(tmp_path))
    instance.config_entries = ConfigEntries(instance, {})
    loader.async_setup(instance)
    device_registry.async_setup(instance)
    await area_registry.async_load(instance)
    await device_registry.async_load(instance)
    await entity_registry.async_load(instance)
    await label_registry.async_load(instance)
    yield instance
    await instance.async_stop(force=True)
