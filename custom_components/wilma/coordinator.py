"""
coordinator.py — DataUpdateCoordinator for the Wilma integration
================================================================
PURPOSE
    The coordinator is the single source of truth for exam and message data.
    It owns the polling loop, calls the Wilma HTTP client, detects new exams
    and messages, and makes the data available to all sensor entities. Only
    one login + HTTP round-trip per data type happens per poll cycle regardless
    of how many sensors exist.

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
        and "wilma_new_message" with the full data dict as event data so
        automations can use the details directly in templates.

    New-exam detection
        Each exam is fingerprinted as "date_iso|topic|subject". On the
        first poll _known_exams is empty so no events fire (avoids a
        flood of notifications on startup). From the second poll onward,
        any key not seen previously triggers an event.

    New-message detection
        Message IDs are incremental, so they serve as a reliable cursor.
        _known_message_ids tracks the set of IDs seen in the previous poll
        per child. First poll populates silently; subsequent polls fire an
        event for each new ID.

    Message filtering
        sender_filters is a list of glob patterns (e.g. ['*smith*']).
        All metadata is fetched in one JSON call, filtered client-side,
        and bodies are fetched only for the top message_limit matches.
        An empty sender_filters list passes all senders through.

    Data structure
        coordinator.data[child_name] = {
            "exams":    [...],   # list of exam dicts
            "messages": [...],   # list of message dicts (with body)
        }

    update_interval
        How often the coordinator polls Wilma. Configured via scan_interval
        in the options flow (default: 4 hours). HA manages the timer.
"""

import fnmatch
import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import WilmaClient
from .const import DOMAIN, EVENT_NEW_EXAM, EVENT_NEW_MESSAGE

_LOGGER = logging.getLogger(__name__)


def _sender_matches(sender: str, patterns: list[str]) -> bool:
    """Return True if sender matches any glob pattern, or if patterns is empty."""
    if not patterns:
        return True
    sender_lower = sender.lower()
    return any(fnmatch.fnmatch(sender_lower, pat.lower()) for pat in patterns)


class WilmaCoordinator(DataUpdateCoordinator):
    def __init__(
        self,
        hass: HomeAssistant,
        base_url: str,
        username: str,
        password: str,
        children: list[dict],
        scan_interval: int,
        sender_filters: list[str],
        message_limit: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = WilmaClient(base_url, username, password)
        self.children = children
        self.sender_filters = sender_filters
        self.message_limit = message_limit
        self._known_exams: dict[str, set] = {}
        self._known_message_ids: dict[str, set] = {}

    async def _async_update_data(self) -> dict:
        try:
            data, new_exam_events, new_message_events = await self.hass.async_add_executor_job(
                self._fetch_all
            )
        except Exception as err:
            raise UpdateFailed(f"Error fetching Wilma data: {err}") from err

        for event_data in new_exam_events:
            self.hass.bus.async_fire(EVENT_NEW_EXAM, event_data)
        for event_data in new_message_events:
            self.hass.bus.async_fire(EVENT_NEW_MESSAGE, event_data)

        return data

    def _fetch_all(self) -> tuple[dict, list[dict], list[dict]]:
        self.client.login()

        result = {}
        new_exam_events = []
        new_message_events = []

        for child in self.children:
            name = child["name"]
            child_id = child["id"]

            # ── Exams ────────────────────────────────────────────────────────
            exams = self.client.get_exams(child_id)

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

            # ── Messages ─────────────────────────────────────────────────────
            # Fetch all metadata (1 call), take the N newest regardless of
            # sender, then filter that window by sender. Bodies are fetched
            # only for the matched subset — at most message_limit HTTP calls.
            all_messages = self.client.get_messages(child_id)
            newest = all_messages[:self.message_limit]
            matched = [
                m for m in newest
                if _sender_matches(m["sender"], self.sender_filters)
            ]

            for msg in matched:
                msg["body"] = self.client.fetch_message_body(child_id, msg["id"])

            known_ids = self._known_message_ids.get(name)
            if known_ids is not None:
                for msg in matched:
                    if msg["id"] not in known_ids:
                        new_message_events.append({"child": name, **msg})
            self._known_message_ids[name] = {m["id"] for m in matched}

            result[name] = {"exams": exams, "messages": matched}

        return result, new_exam_events, new_message_events
