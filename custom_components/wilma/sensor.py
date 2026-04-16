"""
sensor.py — WilmaExamSensor entity
====================================
PURPOSE
    Creates one sensor entity per child in configuration.yaml. Each sensor
    shows the current number of upcoming exams as its state, with the full
    exam list and next-exam details as attributes.

HOW IT WORKS (HA concepts)
    async_setup_platform(hass, config, async_add_entities, ...)
        HA calls this after __init__.py schedules the platform load. We
        pull the coordinator from hass.data and create one entity per
        child. The second argument to async_add_entities (True) tells HA
        to call async_update() on each entity immediately after creation
        so they have data before the first UI render.

    CoordinatorEntity (base class)
        Wires the entity into the coordinator's update cycle. Whenever the
        coordinator finishes a poll and has new data, HA automatically
        calls async_write_ha_state() on every subscribed entity — no
        manual polling or callbacks needed.

    SensorEntity (base class)
        Declares this as a sensor. HA uses native_value and
        native_unit_of_measurement to populate the state in the UI and in
        automations (e.g. state: "3 koetta").

    unique_id
        A stable, unique string HA uses to identify this entity across
        restarts. Without it you cannot rename the entity in the UI or
        store history. It is derived from the child's name so it stays
        consistent even if the entity's display name changes.

    extra_state_attributes
        The dict returned here shows up under the entity in Developer
        Tools → States and is available in automation templates as
        state_attr('sensor.wilma_child_name', 'next_exam_date').
        This is where the exam list lives.
"""

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DOMAIN


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    coordinator = hass.data[DOMAIN]
    async_add_entities(
        [WilmaExamSensor(coordinator, child) for child in coordinator.children],
        True,
    )


class WilmaExamSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, child: dict) -> None:
        super().__init__(coordinator)
        self._child_name = child["name"]
        self._child_id = child["id"]

    @property
    def name(self) -> str:
        return f"Wilma {self._child_name}"

    @property
    def unique_id(self) -> str:
        return f"wilma_{self._child_name.lower().replace(' ', '_')}"

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
