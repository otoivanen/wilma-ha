"""
wilma_client.py — Standalone Wilma test client
================================================
Tests login, lists children, fetches exams and messages.
Messages can be filtered by sender using glob-style patterns
(e.g. '*doe*', '*jane doe*') matched case-insensitively.

Usage:
    python tools/wilma_client.py

You will be prompted for:
    - Wilma base URL  (e.g. https://yourschool.inschool.fi)
    - Username        (your email address)
    - Password
    - Sender filter patterns (comma-separated, leave blank to show all)
"""

import fnmatch
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

    # ── Messages ──────────────────────────────────────────────────────────────

    def get_messages(self, child_id: str) -> list[dict]:
        """
        Fetch metadata for all inbox messages for a child via the JSON list API.
        Does NOT fetch message bodies — call _fetch_message_body() separately
        for only the messages you actually need.

        Endpoint: GET /!{child_id}/messages/list
        Returns:  {"Status": 200, "Messages": [...]}

        Each message object from the API:
          Id          : int  — unique message ID, grows over time (cursor-safe)
          Subject     : str  — message subject
          TimeStamp   : str  — "YYYY-MM-DD HH:MM"
          Sender      : str  — "Lastname Firstname (ShortCode)"
          SenderId    : int  — internal sender ID
          SenderType  : int  — 1=teacher, 3=school staff, 4=guardian reply
          Folder      : str  — "inbox" for inbox messages
          Status      : int|None — 1=unread, absent=read

        The list is already sorted newest-first.
        """
        r = self.session.get(f"{self.base_url}/!{child_id}/messages/list")
        r.raise_for_status()

        data = r.json()
        if data.get("Status") != 200:
            raise RuntimeError(
                f"messages/list returned status {data.get('Status')} for child {child_id}"
            )

        messages = []
        for item in sorted(data.get("Messages", []), key=lambda x: x.get("TimeStamp", ""), reverse=True):
            message_id = str(item["Id"])
            sender = item.get("Sender", "")
            sender_id_match = re.search(r"\(([^)]+)\)$", sender)

            messages.append({
                "id":          message_id,
                "subject":     item.get("Subject", ""),
                "sender":      sender,
                "sender_id":   sender_id_match.group(1) if sender_id_match else "",
                "sender_type": item.get("SenderType"),
                "sent":        item.get("TimeStamp", ""),
                "url":         f"{self.base_url}/!{child_id}/messages/{message_id}",
                "is_unread":   item.get("Status") == 1,
            })

        return messages

    def _fetch_message_body(self, child_id: str, message_id: str) -> str:
        """
        Fetch and return the plain-text body of a single message.
        The body lives in <div class="ckeditor"> (also matched when class is
        "ckeditor hidden" — BS4 does partial class matching).
        """
        r = self.session.get(f"{self.base_url}/!{child_id}/messages/{message_id}")
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        body_div = soup.find("div", class_="ckeditor")
        if not body_div:
            return ""
        text = body_div.get_text("\n", strip=True)
        text = text.replace("\\n", "\n")
        return "\n".join(line for line in text.splitlines() if line.strip())

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

    def print_messages(
        self,
        children: list[dict],
        filters: list[str],
        limit: int = 10,
    ) -> None:
        """
        Fetch metadata for all messages, filter by sender, take the `limit`
        newest matches, then fetch bodies only for those. An empty `filters`
        list matches all senders.
        """
        for child in children:
            print(f"\n{'='*55}")
            print(f"  {child['name']} — Messages")
            print(f"{'='*55}")

            all_messages = self.get_messages(child["id"])

            if not all_messages:
                print("  No messages found.")
                continue

            newest = all_messages[:limit]
            matched = [m for m in newest if _sender_matches(m["sender"], filters)]

            print(
                f"  {len(all_messages)} message(s) in inbox, "
                f"checking {len(newest)} newest, {len(matched)} matched filter."
            )

            if not matched:
                print("  Senders in the last 10:")
                for m in newest:
                    print(f"    {m['sent']}  {repr(m['sender'])}")
                continue

            for msg in matched:
                body = self._fetch_message_body(child["id"], msg["id"])
                unread_tag = " [UNREAD]" if msg["is_unread"] else ""
                print(f"  [{msg['id']}]{unread_tag} {msg['sent']}")
                print(f"     Subject : {msg['subject']}")
                print(f"     Sender  : {msg['sender']} (type={msg['sender_type']})")
                print(f"     Body    :")
                for line in body.splitlines():
                    print(f"               {line}")
                print()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_date_iso(date_str: str) -> str | None:
    match = re.search(r'(\d{1,2})\.(\d{1,2})\.(\d{4})', date_str)
    if match:
        day, month, year = match.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"
    return None


def _sender_matches(sender: str, patterns: list[str]) -> bool:
    """
    Return True if `sender` matches any of the glob patterns, or if `patterns`
    is empty (no filter → everything passes).  Matching is case-insensitive.
    """
    if not patterns:
        return True
    sender_lower = sender.lower()
    return any(fnmatch.fnmatch(sender_lower, pat.lower()) for pat in patterns)


def _parse_filter_input(raw: str) -> list[str]:
    """Parse a comma-separated filter string into a list of stripped patterns."""
    raw = raw.strip().strip("[]")
    if not raw:
        return []
    return [p.strip().strip("'\"") for p in raw.split(",") if p.strip()]


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Wilma test client")
    print("-" * 40)
    base_url = input("Wilma base URL (e.g. https://yourschool.inschool.fi): ").strip()
    username = input("Username (email): ").strip()
    password = getpass.getpass("Password: ")

    print("\nSender filter — comma-separated name patterns, * = wildcard.")
    print("  Type:    *smith*, *jane*")
    print("  Leave blank to show ALL senders.")
    raw_filters = input("Filter: ").strip()
    filters = _parse_filter_input(raw_filters)

    if filters:
        print(f"Active filters: {filters}")
    else:
        print("No filter — all senders will be shown.")

    message_limit = 10  # max bodies to fetch per child after filtering

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
    client.print_messages(children, filters=filters, limit=message_limit)
