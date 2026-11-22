"""Reparationerne "Genstart for at fuldføre/fjerne Wattlas" – med en knap, der genstarter Home Assistant."""
from __future__ import annotations

from homeassistant.components.repairs import ConfirmRepairFlow, RepairsFlow
from homeassistant.core import HomeAssistant


class Genstart(ConfirmRepairFlow):
    async def async_step_confirm(self, user_input=None):
        if user_input is not None:
            await self.hass.services.async_call("homeassistant", "restart")
            return self.async_create_entry(data={})
        return await super().async_step_confirm()  # viser teksten med reparationens pladsholdere (fx backup-mappen)


async def async_create_fix_flow(hass: HomeAssistant, issue_id: str, data) -> RepairsFlow:
    return Genstart()
