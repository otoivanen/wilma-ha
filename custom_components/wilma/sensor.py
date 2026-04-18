"""
sensor.py — WilmaExamSensor and WilmaMessageSensor entities
============================================================
PURPOSE
    Creates two sensor entities per child: one for upcoming exams and one
    for recent messages. Both subscribe to the same coordinator so a single
    poll cycle updates all sensors at once.

HOW IT WORKS (HA concepts)
    async_setup_entry(hass, entry, async_add_entities)
        HA calls this after __init__.py forwards setup to the sensor
        platform. We pull the coordinator from hass.data and create one
        exam sensor and one message sensor per child.

    CoordinatorEntity (base class)
        Wires the entity into the coordinator's update cycle. Whenever the
        coordinator finishes a poll and has new data, HA automatically
        calls async_write_ha_state() on every subscribed entity.

    coordinator.data structure
        coordinator.data[child_name] = {
            "exams":    [...],   # list of exam dicts
            "messages": [...],   # list of message dicts (with body)
        }

    unique_id
        Derived from the config entry ID and child ID so it stays unique
        even across multiple Wilma accounts. Message sensor appends "_msg".

    extra_state_attributes
        Available in automation templates via state_attr(...).
        Exam sensor:    exams, next_exam, next_exam_date
        Message sensor: messages, latest_message
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
    entities = []
    for child in coordinator.children:
        entities.append(WilmaExamSensor(coordinator, child, entry.entry_id))
        entities.append(WilmaMessageSensor(coordinator, child, entry.entry_id))
    async_add_entities(entities, True)


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
    def icon(self) -> str:
        return "mdi:school"

    @property
    def _exams(self) -> list:
        return self.coordinator.data.get(self._child_name, {}).get("exams", [])

    @property
    def native_value(self) -> int | str:
        return len(self._exams) if self._exams else "Ei kokeita"

    @property
    def native_unit_of_measurement(self) -> str | None:
        return "koetta" if self._exams else None

    @property
    def extra_state_attributes(self) -> dict:
        exams = self._exams
        attrs: dict = {"child": self._child_name, "exams": exams}
        if exams:
            attrs["next_exam"] = exams[0]
            attrs["next_exam_date"] = exams[0].get("date_iso")
        return attrs


class WilmaMessageSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, child: dict, entry_id: str) -> None:
        super().__init__(coordinator)
        self._child_name = child["name"]
        self._child_id = child["id"]
        self._entry_id = entry_id

    @property
    def name(self) -> str:
        return f"Wilma {self._child_name} Messages"

    @property
    def unique_id(self) -> str:
        return f"{self._entry_id}_{self._child_id}_msg"

    @property
    def icon(self) -> str:
        return "mdi:message-text"

    @property
    def _messages(self) -> list:
        return self.coordinator.data.get(self._child_name, {}).get("messages", [])

    @property
    def native_value(self) -> int:
        return sum(1 for m in self._messages if m.get("is_unread"))

    @property
    def native_unit_of_measurement(self) -> str | None:
        return "unread" if self.native_value else None

    @property
    def extra_state_attributes(self) -> dict:
        messages = self._messages
        attrs: dict = {"child": self._child_name, "messages": messages}
        if messages:
            attrs["latest_message"] = messages[0]
        return attrs
