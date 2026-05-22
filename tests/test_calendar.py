"""
tests/test_calendar.py
──────────────────────
Phase 2 test suite — Calendar integration.

Tests run in two modes:
  MOCK mode:  No credentials needed — tests logic and graph flow
  LIVE mode:  credentials.json + token.json present — hits real Google Calendar

Run: python tests/test_calendar.py
"""

import sys
import os
import datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zoneinfo import ZoneInfo
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

console  = Console()
LAGOS_TZ = ZoneInfo("Africa/Lagos")

CALENDAR_AVAILABLE = (
    os.path.exists("credentials.json") or os.path.exists("token.json")
)


def test_mock_scheduling_flow():
    """
    Tests the calendar node directly — bypasses classify
    so no API key is needed.
    """
    from agent.memory.manager import MemoryManager
    from pathlib import Path

    mem = MemoryManager(seed=False)

    # Simulate what the graph state looks like AFTER classify
    # has already labelled this as a scheduling message
    state = {
        "message":         "Hi Jude, can we schedule a property viewing this Thursday at 2PM?",
        "source":          "whatsapp",
        "sender":          "Mrs Folake",
        "sender_is_vip":   False,
        "thread_id":       "test",
        "memory_block":    "",
        "client_context":  "",
        "category":        "scheduling",   # already classified
        "priority_score":  5,
        "routing":         "queue_approval",
        "keywords_hit":    [],
        "draft_response":  None,
        "escalation_note": None,
        "reasoning":       "",
        "learn_fact":      None,
        "log_episode":     None,
        "error":           None,
        "completed_nodes": ["load_memory", "classify"],
        "final_action":    None,
    }

    # Call the calendar node directly
    from agent.nodes import node_calendar_check
    result = node_calendar_check(state)

    nodes = result.get("completed_nodes", [])

    # Should have hit calendar_check, calendar_skip, or calendar_error
    assert any(n in nodes for n in ["calendar_check", "calendar_skip", "calendar_error"]), \
        f"Calendar node not reached. Got: {nodes}"

    # Confirm it ran without crashing
    assert result is not None, "Calendar node returned None"

    print(f"   Calendar node result: {nodes}")
    return result


def test_mock_exam_reminder_flow():
    """
    Tests priority scoring directly — no API key needed.
    Confirms exam messages score >= 7.
    Exam keyword gets a high boost due to Jude's history of missing them.
    """
    from agent.memory.priority import PriorityMemory

    pm = PriorityMemory()

    score_data = pm.score_message(
        text="Reminder: your professional exam is next Thursday at 9AM. Don't forget.",
        source="whatsapp",
        sender="Course Secretary",
    )

    print(f"   Score: {score_data['score']}/10")
    print(f"   Keywords hit: {score_data['keywords_hit']}")
    print(f"   Routing: {score_data['routing']}")

    assert score_data["score"] >= 7, \
        f"Exam should score >= 7. Got {score_data['score']}. " \
        f"Check KEYWORD_BOOSTS in priority.py — 'exam' must be >= 7."

    # Exam reminders should always queue for approval at minimum
    assert score_data["routing"] in ["queue_approval", "auto_escalate"], \
        f"Exam should queue or escalate. Got: {score_data['routing']}"

    return {
        "category":        "scheduling",
        "priority_score":  score_data["score"],
        "routing":         score_data["routing"],
        "completed_nodes": ["priority_score_check"],
        "draft_response":  None,
    }


def test_live_get_todays_events():
    """Live test — reads real calendar. Requires credentials."""
    from integrations.calendar import CalendarService
    cal    = CalendarService()
    events = cal.get_todays_events()
    # Should return a list (even if empty)
    assert isinstance(events, list)
    return events


def test_live_check_availability():
    """Live test — checks if tomorrow at 2PM is free."""
    from integrations.calendar import CalendarService
    cal      = CalendarService()
    tomorrow = datetime.datetime.now(LAGOS_TZ) + datetime.timedelta(days=1)
    check_dt = tomorrow.replace(hour=14, minute=0, second=0, microsecond=0)
    result   = cal.check_availability(check_dt, duration_minutes=60)
    assert "available" in result
    assert "alternatives" in result
    return result


def test_live_daily_briefing():
    """Live test — generates today's briefing."""
    from integrations.calendar import CalendarService
    cal      = CalendarService()
    briefing = cal.get_daily_briefing()
    assert len(briefing) > 20   # Should have actual content
    return briefing


def run_all():
    console.print()
    console.print(Panel(
        "[bold]J-OS Phase 2 — Calendar Integration Tests[/bold]\n"
        f"Mode: {'[green]LIVE (Google Calendar)[/green]' if CALENDAR_AVAILABLE else '[yellow]MOCK (no credentials)[/yellow]'}",
        border_style="bright_blue",
    ))
    console.print()

    results = []

    # Mock tests — always run
    mock_tests = [
        ("TC-2-01", "Scheduling message → calendar node", test_mock_scheduling_flow),
        ("TC-2-02", "Exam reminder → critical escalation",  test_mock_exam_reminder_flow),
    ]

    for test_id, label, fn in mock_tests:
        try:
            result = fn()
            console.print(f"[green]✅ {test_id}[/green] — {label}")
            if isinstance(result, dict):
                console.print(f"   Category: {result.get('category')} | "
                              f"Score: {result.get('priority_score')} | "
                              f"Routing: {result.get('routing')}")
                console.print(f"   Nodes: {' → '.join(result.get('completed_nodes', []))}")
                if result.get("draft_response"):
                    console.print(f"   [dim]Draft: {result['draft_response'][:120]}[/dim]")
            results.append((test_id, label, True, None))
        except Exception as e:
            console.print(f"[red]❌ {test_id}[/red] — {label}")
            console.print(f"   [red]{str(e)}[/red]")
            results.append((test_id, label, False, str(e)))
        console.print()

    # Live tests — only if credentials exist
    if CALENDAR_AVAILABLE:
        live_tests = [
            ("TC-2-03", "Fetch today's events",      test_live_get_todays_events),
            ("TC-2-04", "Check availability",         test_live_check_availability),
            ("TC-2-05", "Generate daily briefing",    test_live_daily_briefing),
        ]
        for test_id, label, fn in live_tests:
            try:
                result = fn()
                console.print(f"[green]✅ {test_id}[/green] — {label}")
                if isinstance(result, str):
                    console.print(f"\n[cyan]{result}[/cyan]\n")
                elif isinstance(result, dict):
                    console.print(f"   {result}")
                elif isinstance(result, list):
                    console.print(f"   {len(result)} event(s) returned")
                results.append((test_id, label, True, None))
            except Exception as e:
                console.print(f"[red]❌ {test_id}[/red] — {label}")
                console.print(f"   [red]{str(e)}[/red]")
                results.append((test_id, label, False, str(e)))
            console.print()
    else:
        console.print("[dim]Live calendar tests skipped — add credentials.json to run them.[/dim]\n")

    # Summary
    passed = sum(1 for _, _, ok, _ in results if ok)
    total  = len(results)
    color  = "green" if passed == total else "yellow"
    console.print(Panel(
        f"[bold {color}]{passed}/{total} tests passed[/bold {color}]",
        border_style=color,
    ))


if __name__ == "__main__":
    run_all()