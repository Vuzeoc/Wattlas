"""Om EMHASS-nøglen er sat – aldrig nøglen selv. Startspærren (binary_sensor.wattlas_konfigureret) bruger den."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import NOEGLE_SAT


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    async_add_entities([NoegleSat(entry)])


class NoegleSat(BinarySensorEntity):
    _attr_name = "Wattlas EMHASS-nøgle sat"
    _attr_unique_id = "wattlas_emhass_noegle_sat"
    _attr_icon = "mdi:key"
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self.entity_id = NOEGLE_SAT
        self._attr_is_on = bool(entry.data.get("emhass_noegle"))

    async def async_added_to_hass(self) -> None:
        async def aendret(_hass, entry) -> None:
            self._attr_is_on = bool(entry.data.get("emhass_noegle"))
            self.async_write_ha_state()
        self.async_on_remove(self._entry.add_update_listener(aendret))
