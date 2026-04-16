"""
sensor.py — WilmaExamSensor entity
====================================
PURPOSE
    Creates one sensor entity per child discovered during config flow.
    Each sensor shows the current number of upcoming exams as its state,
    with the full exam list and next-exam details as attributes.

HOW IT WORKS (HA concepts)
    async_setup_entry(hass, entry, async_add_entities)
        HA calls this after __init__.py forwards setup to the sensor
        platform. We pull the coordinator from hass.data and create one
        entity per child.

    CoordinatorEntity (base class)
        Wires the entity into the coordinator's update cycle. Whenever the
        coordinator finishes a poll and has new data, HA automatically
        calls async_write_ha_state() on every subscribed entity.

    SensorEntity (base class)
        Declares this as a sensor. HA uses native_value and
        native_unit_of_measurement to populate the state.

    unique_id
        A stable string HA uses to identify this entity across restarts.
        Derived from the config entry ID and child ID so it stays unique
        even across multiple Wilma accounts.

    extra_state_attributes
        The dict returned here shows up under the entity in Developer
        Tools → States and is available in automation templates as
        state_attr('sensor.wilma_child_name', 'next_exam_date').
"""

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [WilmaExamSensor(coordinator, child, entry.entry_id) for child in coordinator.children],
        True,
    )


class WilmaExamSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, child: dict, entry_id: str) -> None:
        super().__init__(coordinator)
        self._child_name = child["name"]
        self._child_id = child["id"]
        self._entry_id = entry_id

    @property
    def name(self) -> str:
        return f"Wilma {self._child_name}"

    @property
    def unique_id(self) -> str:
        return f"{self._entry_id}_{self._child_id}"

    @property
    def native_value(self) -> int | str:
        exams = self.coordinator.data.get(self._child_name, [])
        return len(exams) if exams else "Ei kokeita"

    @property
    def native_unit_of_measurement(self) -> str | None:
        exams = self.coordinator.data.get(self._child_name, [])
        return "koetta" if exams else None

    @property
    def icon(self) -> str:
        return "mdi:school"

    @property
    def extra_state_attributes(self) -> dict:
        exams = self.coordinator.data.get(self._child_name, [])
        attrs: dict = {
            "child": self._child_name,
            "exams": exams,
        }
        if exams:
            attrs["next_exam"] = exams[0]
            attrs["next_exam_date"] = exams[0].get("date_iso")
        return attrs
