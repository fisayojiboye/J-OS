"""
integrations/calendar.py
────────────────────────
Google Calendar integration for the Jude Agent.

Handles:
  - Authentication (OAuth2, auto-refresh)
  - Reading Jude's schedule
  - Checking availability for a proposed time
  - Booking new appointments
  - Sending structured reminders
  - Generating the daily briefing
  - Detecting scheduling conflicts
"""

import os
import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# The only permission scope I need.
# Read/write access to calendar events.
# If I change this later, delete token.json and re-authenticate.
SCOPES = ["https://www.googleapis.com/auth/calendar"]

# Lagos timezone. Every time he create or read events,
# we convert to/from this. Never store naive datetimes.
LAGOS_TZ = ZoneInfo("Africa/Lagos")

# Where credential files live
CREDENTIALS_FILE = Path("credentials.json")
TOKEN_FILE        = Path("token.json")

# Jude's working hours. Agent won't book outside these.
WORK_START_HOUR = 9    # 9AM
WORK_END_HOUR   = 20   # 8PM

class CalendarService:
    """
    Wrapper around the Google Calendar API.
    All methods are safe — they catch errors and return
    structured results instead of crashing the agent.
    """

    def __init__(self):
        self._service = None
        self._authenticate()

    def _authenticate(self) -> None:
        """
        Handles OAuth2 authentication.

        First run:   opens browser for Jude to log in and grant access.
                     Saves token.json so this never happens again.
        Later runs:  loads token.json silently.
                     If the token is expired, refreshes it automatically.
        """
        creds = None

        # If token.json exists, load the saved credentials
        if TOKEN_FILE.exists():
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

        # If credentials don't exist or are expired
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                # Token exists but expired — refresh silently (no browser needed)
                creds.refresh(Request())
            else:
                # First time — open browser for login
                if not CREDENTIALS_FILE.exists():
                    raise FileNotFoundError(
                        "credentials.json not found. "
                        "Download it from Google Cloud Console and place it in the project root."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(CREDENTIALS_FILE), SCOPES
                )
                # This opens a browser window for Jude to log in
                creds = flow.run_local_server(port=0)

            # Save the credentials for next time
            TOKEN_FILE.write_text(creds.to_json())

        # Build the actual API client
        self._service = build("calendar", "v3", credentials=creds)

    def get_todays_events(self) -> list[dict]:
        """
        Fetch all of Jude's events for today.
        Returns a clean list of dicts — not raw Google API objects.

        Called by: daily briefing generator
        """
        # Start of today in Lagos time
        now = datetime.datetime.now(LAGOS_TZ)
        start_of_day = now.replace(hour=0,  minute=0,  second=0,  microsecond=0)
        end_of_day   = now.replace(hour=23, minute=59, second=59, microsecond=0)

        return self._fetch_events(start_of_day, end_of_day)
    
    def get_upcoming_events(self, days: int = 7) -> list[dict]:
        """
        Fetch events for the next N days.
        Used by the agent to give Jude a week overview.
        """
        now = datetime.datetime.now(LAGOS_TZ)
        end = now + datetime.timedelta(days=days)
        return self._fetch_events(now, end)
    
    def check_availability(
        self,
        proposed_dt: datetime.datetime,
        duration_minutes: int = 60,
    ) -> dict:
        """
        Check if Jude is free at a proposed date/time.

        Args:
            proposed_dt:      The datetime to check (must be timezone-aware).
            duration_minutes: How long the event would be. Default 1 hour.

        Returns:
            {
              "available": True/False,
              "conflict": event dict if conflict exists, else None,
              "alternatives": list of free slots that day if not available
            }
        """
        # Make sure it's in Lagos time
        if proposed_dt.tzinfo is None:
            proposed_dt = proposed_dt.replace(tzinfo=LAGOS_TZ)

        end_dt = proposed_dt + datetime.timedelta(minutes=duration_minutes)

        # Check working hours — agent respects Jude's personal time
        if proposed_dt.hour < WORK_START_HOUR or end_dt.hour > WORK_END_HOUR:
            return {
                "available":    False,
                "conflict":     None,
                "reason":       f"Outside working hours ({WORK_START_HOUR}AM–{WORK_END_HOUR}PM Lagos time)",
                "alternatives": self._find_free_slots(proposed_dt.date(), duration_minutes),
            }

        # Fetch events that overlap with the proposed window
        events = self._fetch_events(proposed_dt, end_dt)

        if events:
            return {
                "available":    False,
                "conflict":     events[0],   # The first conflicting event
                "reason":       f"Conflict with: {events[0]['title']}",
                "alternatives": self._find_free_slots(proposed_dt.date(), duration_minutes),
            }

        return {
            "available":    True,
            "conflict":     None,
            "reason":       "Free",
            "alternatives": [],
        }
    
    def book_event(
        self,
        title:            str,
        start_dt:         datetime.datetime,
        duration_minutes: int   = 60,
        description:      str   = "",
        attendee_email:   str   = None,
        reminders:        list  = None,
    ) -> dict:
        """
        Create a new event in Jude's Google Calendar.

        Args:
            title:            Event name
            start_dt:         When it starts (Lagos time)
            duration_minutes: How long
            description:      Optional notes
            attendee_email:   If set, Google sends them a calendar invite
            reminders:        List of {"method": "popup"/"email", "minutes": N}
                              If None, uses Jude's default reminders.

        Returns:
            {"success": True, "event_id": "...", "link": "...", "event": {...}}
            or
            {"success": False, "error": "..."}
        """
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=LAGOS_TZ)

        end_dt = start_dt + datetime.timedelta(minutes=duration_minutes)

        # Default reminders if none specified:
        # 1 day before (email) + 1 hour before (popup on phone)
        if reminders is None:
            reminders = [
                {"method": "email",  "minutes": 24 * 60},   # 1 day before
                {"method": "popup",  "minutes": 60},         # 1 hour before
            ]

        # Build the event body Google expects
        event_body = {
            "summary":     title,
            "description": description,
            "start": {
                "dateTime": start_dt.isoformat(),
                "timeZone": "Africa/Lagos",
            },
            "end": {
                "dateTime": end_dt.isoformat(),
                "timeZone": "Africa/Lagos",
            },
            "reminders": {
                "useDefault": False,
                "overrides":  reminders,
            },
        }

        # Add attendee if provided — Google sends them an invite automatically
        if attendee_email:
            event_body["attendees"] = [{"email": attendee_email}]

        try:
            event = self._service.events().insert(
                calendarId="primary",   # Jude's main calendar
                body=event_body,
                sendUpdates="all",      # Send email invites to attendees
            ).execute()

            return {
                "success":  True,
                "event_id": event["id"],
                "link":     event.get("htmlLink", ""),
                "event":    self._clean_event(event),
            }

        except HttpError as e:
            return {
                "success": False,
                "error":   f"Google Calendar API error: {str(e)}",
            }
        
    def add_critical_reminders(
        self,
        event_title:  str,
        event_dt:     datetime.datetime,
        event_id:     str = None,
    ) -> list[dict]:
        """
        For critical events (exams, court dates, payment deadlines):
        Add layered reminders at 1 week, 3 days, 1 day, and 3 hours before.

        This is the direct response to Jude's exam incident.
        Called automatically when episodic memory flags an event as critical.

        Returns a list of reminder events created.
        """
        if event_dt.tzinfo is None:
            event_dt = event_dt.replace(tzinfo=LAGOS_TZ)

        # The reminder schedule — escalating urgency
        reminder_schedule = [
            (7 * 24 * 60,  "1 week"),    # 7 days before
            (3 * 24 * 60,  "3 days"),    # 3 days before
            (24 * 60,      "1 day"),     # 1 day before
            (3 * 60,       "3 hours"),   # 3 hours before
        ]

        created = []
        for minutes_before, label in reminder_schedule:
            reminder_dt = event_dt - datetime.timedelta(minutes=minutes_before)

            # Only create reminders in the future — no point creating a
            # "1 week before" reminder if the event is 2 days away
            if reminder_dt > datetime.datetime.now(LAGOS_TZ):
                result = self.book_event(
                    title=f"🚨 REMINDER — {label} before: {event_title}",
                    start_dt=reminder_dt,
                    duration_minutes=15,
                    description=(
                        f"Critical reminder for: {event_title}\n"
                        f"Event scheduled: {event_dt.strftime('%A %d %B %Y at %I:%M %p')}\n"
                        f"This is a {label} reminder."
                    ),
                    reminders=[
                        {"method": "popup", "minutes": 0},    # Alert exactly at reminder time
                        {"method": "email", "minutes": 0},    # Email too
                    ],
                )
                if result["success"]:
                    created.append(result["event"])

        return created
    
    def get_daily_briefing(self) -> str:
        """
        Generate Jude's morning briefing from his actual calendar.
        Formatted for WhatsApp/Telegram delivery.

        Called every morning at 7AM by the scheduler (Phase 5).
        """
        now    = datetime.datetime.now(LAGOS_TZ)
        today  = now.strftime("%A, %d %B %Y")
        events = self.get_todays_events()

        lines = [f"☀️ Good morning Jude — {today}\n"]

        if not events:
            lines.append("📅 Your calendar is clear today.")
        else:
            lines.append(f"📅 You have {len(events)} commitment(s) today:\n")
            for i, event in enumerate(events, 1):
                time_str = event.get("start_time", "All day")
                lines.append(f"  {i}. {time_str} — {event['title']}")
                if event.get("description"):
                    # Only first line of description in briefing
                    desc_line = event["description"].split("\n")[0]
                    lines.append(f"     {desc_line}")

        # Check for anything critical in next 7 days
        upcoming = self.get_upcoming_events(days=7)
        critical_keywords = ["exam", "court", "deadline", "payment due", "signing", "legal"]
        critical = [
            e for e in upcoming
            if any(kw in e["title"].lower() for kw in critical_keywords)
        ]

        if critical:
            lines.append("\n⚠️ Critical items in next 7 days:")
            for e in critical:
                lines.append(f"  • {e['start_date']} — {e['title']}")

        lines.append("\nHave a productive day. 🏠")
        return "\n".join(lines)
    
    def _fetch_events(
        self,
        start: datetime.datetime,
        end:   datetime.datetime,
    ) -> list[dict]:
        """
        Internal method — fetch raw events from Google and clean them.
        Not called directly outside this class.
        """
        try:
            result = self._service.events().list(
                calendarId="primary",
                timeMin=start.isoformat(),
                timeMax=end.isoformat(),
                singleEvents=True,       # Expand recurring events into individual instances
                orderBy="startTime",     # Chronological order
            ).execute()

            return [self._clean_event(e) for e in result.get("items", [])]

        except HttpError as e:
            # Log but don't crash — return empty list
            print(f"[CalendarService] Error fetching events: {e}")
            return []
        
    def _clean_event(self, raw_event: dict) -> dict:
        """
        Convert Google's verbose event format into a clean dict
        we control. Insulates the rest of the codebase from Google's schema.

        If Google changes their API response format one day,
        we only fix this one function.
        """
        start = raw_event.get("start", {})
        end   = raw_event.get("end",   {})

        # Events can be "dateTime" (timed) or "date" (all-day)
        start_str = start.get("dateTime") or start.get("date", "")
        end_str   = end.get("dateTime")   or end.get("date",   "")

        # Parse start time for display
        start_time_display = ""
        start_date_display = ""
        if "T" in start_str:   # It's a dateTime, not an all-day date
            dt = datetime.datetime.fromisoformat(start_str)
            dt = dt.astimezone(LAGOS_TZ)
            start_time_display = dt.strftime("%I:%M %p")   # "02:30 PM"
            start_date_display = dt.strftime("%a %d %b")   # "Thu 22 May"
        else:
            start_date_display = start_str
            start_time_display = "All day"

        return {
            "id":          raw_event.get("id", ""),
            "title":       raw_event.get("summary", "No title"),
            "description": raw_event.get("description", ""),
            "start_time":  start_time_display,
            "start_date":  start_date_display,
            "start_raw":   start_str,
            "end_raw":     end_str,
            "link":        raw_event.get("htmlLink", ""),
            "attendees":   [
                a.get("email", "") for a in raw_event.get("attendees", [])
            ],
        }

    def _find_free_slots(
        self,
        date:             datetime.date,
        duration_minutes: int = 60,
    ) -> list[str]:
        """
        Find available time slots on a given date.
        Returns human-readable strings like ["2:00 PM", "3:30 PM", "5:00 PM"].

        Called when check_availability finds a conflict —
        so the agent can immediately suggest alternatives.
        """
        # Build list of candidate slots every 30 mins during working hours
        candidates = []
        current = datetime.datetime.combine(
            date,
            datetime.time(WORK_START_HOUR, 0),
            tzinfo=LAGOS_TZ,
        )
        day_end = datetime.datetime.combine(
            date,
            datetime.time(WORK_END_HOUR, 0),
            tzinfo=LAGOS_TZ,
        )

        while current + datetime.timedelta(minutes=duration_minutes) <= day_end:
            candidates.append(current)
            current += datetime.timedelta(minutes=30)

        # Fetch all events that day
        start_of_day = datetime.datetime.combine(date, datetime.time(0, 0), tzinfo=LAGOS_TZ)
        end_of_day   = datetime.datetime.combine(date, datetime.time(23, 59), tzinfo=LAGOS_TZ)
        busy_events  = self._fetch_events(start_of_day, end_of_day)

        # Filter out candidates that overlap with existing events
        free_slots = []
        for slot_start in candidates:
            slot_end = slot_start + datetime.timedelta(minutes=duration_minutes)
            is_free  = True

            for event in busy_events:
                if not event["start_raw"] or "T" not in event["start_raw"]:
                    continue   # Skip all-day events for slot finding

                ev_start = datetime.datetime.fromisoformat(event["start_raw"]).astimezone(LAGOS_TZ)
                ev_end   = datetime.datetime.fromisoformat(event["end_raw"]).astimezone(LAGOS_TZ)

                # Check overlap: slot starts before event ends AND slot ends after event starts
                if slot_start < ev_end and slot_end > ev_start:
                    is_free = False
                    break

            if is_free:
                free_slots.append(slot_start.strftime("%I:%M %p"))

            # Return max 3 alternatives — enough choice without overwhelming
            if len(free_slots) >= 3:
                break

        return free_slots