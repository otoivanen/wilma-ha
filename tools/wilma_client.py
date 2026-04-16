"""
wilma_client.py — Standalone Wilma test client
================================================
Use this to verify connectivity, test login, and discover the child IDs
and names registered to your Wilma account before setting up the HA
integration.

Usage:
    python tools/wilma_client.py

You will be prompted for:
    - Wilma base URL  (e.g. https://yourschool.inschool.fi)
    - Username        (your email address)
    - Password

The script will log in, print all children found on the account with their
IDs, and then print each child's upcoming exams.
"""

import getpass
import re
import sys

import requests
from bs4 import BeautifulSoup


# ── Client ────────────────────────────────────────────────────────────────────

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
        """Log in to Wilma. Resets the session first to avoid stale cookies."""
        self.session = requests.Session()
        self.session.headers.update(self._HEADERS)

        r = self.session.get(f"{self.base_url}/login")
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        session_input = soup.find("input", {"name": "SESSIONID"})
        if session_input is None:
            raise RuntimeError(
                f"SESSIONID not found on login page (status {r.status_code}, url {r.url})"
            )

        r = self.session.post(
            f"{self.base_url}/login",
            data={
                "Login":      self.username,
                "Password":   self.password,
                "SESSIONID":  session_input["value"],
                "returnpath": "",
                "submit":     "Kirjaudu sisään",
            },
            allow_redirects=True,
        )
        r.raise_for_status()

        if "Kirjaudu sisään" in r.text and 'name="Login"' in r.text:
            raise RuntimeError("Login failed – check your username/password")

        print("Login successful.")

    # ── Children ──────────────────────────────────────────────────────────────

    def get_children(self) -> list[dict]:
        """
        Discover children linked to the logged-in account by parsing the
        Wilma home page. Returns a list of dicts with 'name' and 'id' keys.

        Child links follow the pattern /!{child_id}/ in the page HTML.
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
        """Fetch upcoming exams for a child."""
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

    # ── Pretty-print ──────────────────────────────────────────────────────────

    def print_children(self, children: list[dict]) -> None:
        print(f"\nFound {len(children)} child(ren):")
        for child in children:
            print(f"  {child['name']:<30}  id: {child['id']}")

    def print_exams(self, children: list[dict]) -> None:
        for child in children:
            print(f"\n{'='*55}")
            print(f"  {child['name']}")
            print(f"{'='*55}")
            exams = self.get_exams(child["id"])

            if not exams:
                print("  No upcoming exams.")
                continue

            for exam in exams:
                print(f"\n  {exam.get('date', '?')}")
                print(f"     Topic   : {exam.get('topic', '?')}")
                print(f"     Subject : {exam.get('subject', '?').strip()}")
                print(f"     Teacher : {exam.get('teacher', '?')}")
                if exam.get("details"):
                    print(f"     Details : {exam['details']}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_date_iso(date_str: str) -> str | None:
    match = re.search(r'(\d{1,2})\.(\d{1,2})\.(\d{4})', date_str)
    if match:
        day, month, year = match.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"
    return None


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Wilma test client")
    print("-" * 40)
    base_url = input("Wilma base URL (e.g. https://yourschool.inschool.fi): ").strip()
    username = input("Username (email): ").strip()
    password = getpass.getpass("Password: ")

    client = WilmaClient(base_url, username, password)

    try:
        client.login()
    except RuntimeError as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)

    children = client.get_children()

    if not children:
        print(
            "\nNo children found. The get_children() parser may need adjusting "
            "for your Wilma instance — check the page HTML at GET /",
            file=sys.stderr,
        )
        sys.exit(1)

    client.print_children(children)
    client.print_exams(children)
