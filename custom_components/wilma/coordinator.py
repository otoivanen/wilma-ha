"""
coordinator.py — DataUpdateCoordinator for the Wilma integration
================================================================
PURPOSE
    The coordinator is the single source of truth for exam data. It owns
    the polling loop, calls the Wilma HTTP client, detects new exams, and
    makes the data available to all sensor entities. Only one HTTP round-
    trip happens per poll cycle regardless of how many sensors exist.

HOW IT WORKS (HA concepts)
    DataUpdateCoordinator (HA base class)
        A helper HA provides for the "poll once, share with many" pattern.
        It manages the update_interval timer and calls _async_update_data()
        on schedule. All entities that subscribe to the coordinator are
        automatically refreshed when new data arrives.

    _async_update_data()
        The method HA calls on each poll. It must return the new data dict
        or raise UpdateFailed (which HA turns into a sensor "unavailable"
        state with a log entry). After the executor job returns we fire
        events safely from the async context.

    async_add_executor_job()
        The requests library is blocking (synchronous). HA runs on an
        asyncio event loop, so blocking calls must be run in a thread pool
        via async_add_executor_job. This keeps the event loop free while
        the HTTP calls are in flight.

    hass.bus.async_fire()
        Fires a named event onto the HA event bus. Any automation with a
        matching event trigger will be woken up. We fire "wilma_new_exam"
        with the full exam dict as event data so automations can use the
        details directly in templates.

    New-exam detection
        Each exam is fingerprinted as "date_iso|topic|subject". On the
        first poll _known_exams is empty so no events fire (avoids a
        flood of notifications on startup). From the second poll onward,
        any key not seen previously triggers an event.

    update_interval
        How often the coordinator polls Wilma. Configured via
        scan_interval in configuration.yaml (default: 4 hours). HA
        manages the timer automatically.
"""

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import WilmaClient
from .const import DOMAIN, EVENT_NEW_EXAM

_LOGGER = logging.getLogger(__name__)


class WilmaCoordinator(DataUpdateCoordinator):
    def __init__(
        self,
        hass: HomeAssistant,
        base_url: str,
        username: str,
        password: str,
        children: list[dict],
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = WilmaClient(base_url, username, password)
        self.children = children
        self._known_exams: dict[str, set] = {}

    async def _async_update_data(self) -> dict:
        try:
            data, new_exam_events = await self.hass.async_add_executor_job(
                self._fetch_all
            )
        except Exception as err:
            raise UpdateFailed(f"Error fetching Wilma data: {err}") from err

        for event_data in new_exam_events:
            self.hass.bus.async_fire(EVENT_NEW_EXAM, event_data)

        return data

    def _fetch_all(self) -> tuple[dict, list[dict]]:
        self.client.login()

        result = {}
        new_exam_events = []

        for child in self.children:
            name = child["name"]
            child_id = child["id"]
            exams = self.client.get_exams(child_id)
            result[name] = exams

            current_keys = {
                f"{e.get('date_iso')}|{e.get('topic')}|{e.get('subject')}"
                for e in exams
            }
            known_keys = self._known_exams.get(name)

            if known_keys is not None:
                new_keys = current_keys - known_keys
                for exam in exams:
                    key = f"{exam.get('date_iso')}|{exam.get('topic')}|{exam.get('subject')}"
                    if key in new_keys:
                        new_exam_events.append({"child": name, **exam})

            self._known_exams[name] = current_keys

        return result, new_exam_events
