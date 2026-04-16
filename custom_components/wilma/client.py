"""
client.py — Wilma HTTP client (pure Python, no HA dependencies)
===============================================================
PURPOSE
    Handles all communication with the Wilma school portal: login,
    discovering children linked to the account, and fetching upcoming
    exams for a given child. This file has no knowledge of Home Assistant
    — it is a plain Python module that coordinator.py calls from a
    background thread.

HOW IT WORKS
    WilmaClient wraps a requests.Session that is re-used across calls so
    the login cookie stays alive. Callers must call login() before
    get_children() or get_exams(). The coordinator does this on every
    poll so the session is always fresh (Wilma sessions expire).

    Session cookie bug: After the first successful login, Wilma redirects
    GET /login to the home page because the session already has valid
    cookies. This causes 'NoneType' object is not subscriptable when we
    try to read the SESSIONID. Fixed by resetting self.session at the
    start of every login() call.

    get_children() returns a list of {name, id} dicts discovered by
    parsing the Wilma home page after login. Child links follow the
    pattern /!{child_id}/ in the page HTML.

    get_exams() returns a list of plain dicts. One extra field compared
    to the raw Wilma data is date_iso (ISO-8601 date string, e.g.
    "2026-04-14") — this makes date comparisons in automations easy
    without parsing Finnish weekday names.
"""

import logging
import re
import requests
from bs4 import BeautifulSoup

_LOGGER = logging.getLogger(__name__)


def _parse_date_iso(date_str: str) -> str | None:
    """Parse Finnish exam date like 'Ti 14.4.2026' to '2026-04-14'."""
    match = re.search(r'(\d{1,2})\.(\d{1,2})\.(\d{4})', date_str)
    if match:
        day, month, year = match.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"
    return None


class WilmaClient:
    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "fi-FI,fi;q=0.9,en;q=0.8",
    }

    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.headers.update(self._HEADERS)

    # ── Auth ──────────────────────────────────────────────────────────────────

    def login(self) -> None:
        # Reset session before each login so stale cookies from a previous
        # poll don't cause Wilma to redirect /login → home page.
        self.session = requests.Session()
        self.session.headers.update(self._HEADERS)
        r = self.session.get(f"{self.base_url}/login")
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        session_input = soup.find("input", {"name": "SESSIONID"})
        if session_input is None:
            _LOGGER.error(
                "SESSIONID not found on Wilma login page. "
                "Status: %s, URL: %s, Body snippet: %.500s",
                r.status_code, r.url, r.text,
            )
            raise RuntimeError(
                f"SESSIONID input not found on login page (status {r.status_code}, url {r.url})"
            )
        session_id = session_input["value"]

        r = self.session.post(
            f"{self.base_url}/login",
            data={
                "Login":      self.username,
                "Password":   self.password,
                "SESSIONID":  session_id,
                "returnpath": "",
                "submit":     "Kirjaudu sisään",
            },
            allow_redirects=True,
        )
        r.raise_for_status()

        if "Kirjaudu sisään" in r.text and 'name="Login"' in r.text:
            raise RuntimeError("Login failed – check your username/password")

    # ── Children ──────────────────────────────────────────────────────────────

    def get_children(self) -> list[dict]:
        """
        Discover children linked to the logged-in account by parsing the
        Wilma home page. Returns a list of dicts with 'name' and 'id' keys.

        Child links follow the pattern /!{child_id}/ in the page HTML.
        Must be called after login().
        """
        r = self.session.get(f"{self.base_url}/")
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        seen: dict[str, str] = {}
        for a in soup.find_all("a", href=re.compile(r"^/!\d+")):
            m = re.match(r"^/!(\d+)/", a["href"])
            if m:
                child_id = m.group(1)
                # Use only the first text node — the link may contain nested
                # elements with school/class info that must not be included.
                name = next(a.strings, "").strip()
                if child_id not in seen and name:
                    seen[child_id] = name

        return [{"name": name, "id": cid} for cid, name in seen.items()]

    # ── Exams ─────────────────────────────────────────────────────────────────

    def get_exams(self, child_id: str) -> list[dict]:
        """
        Fetch upcoming exams for a child from /!{child_id}/exams/calendar.

        Returns a list of dicts with keys:
          date, date_iso, topic, subject, group, group_url, teacher, details
        """
        r = self.session.get(f"{self.base_url}/!{child_id}/exams/calendar")
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")
        exams = []

        for table in soup.select("div.table-responsive table.table-grey"):
            rows = table.find_all("tr")
            if not rows:
                continue

            exam = {}

            for i, row in enumerate(rows):
                cells = row.find_all(["td", "th"])
                if len(cells) < 2:
                    continue

                label = cells[0].get_text(strip=True)
                value = cells[1].get_text(" ", strip=True)

                if i == 0:
                    exam["date"] = label
                    exam["date_iso"] = _parse_date_iso(label)

                    parts = [p.strip() for p in value.split(":")]
                    exam["topic"]   = parts[0] if len(parts) > 0 else value
                    exam["subject"] = parts[1] if len(parts) > 1 else ""
                    exam["group"]   = parts[2] if len(parts) > 2 else ""

                    link = cells[1].find("a")
                    exam["group_url"] = (self.base_url + link["href"]) if link else None

                else:
                    if label == "Opettaja":
                        exam["teacher"] = value
                    elif label == "Kokeen lisätiedot":
                        exam["details"] = value
                    else:
                        exam[label] = value

            exams.append(exam)

        return exams
