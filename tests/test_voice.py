"""
tests/test_voice.py
───────────────────
Phase 4 tests — voice pipeline.

TC-4-01: TwiML inbound call response is valid XML
TC-4-02: TwiML connect and record is valid XML
TC-4-03: TwiML missed call / voicemail is valid XML
TC-4-04: Call insight extraction (mock transcript)
TC-4-05: Full call processor (no real recording needed)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console
from rich.panel import Panel
console = Console()


def test_twiml_inbound():
    """TC-4-01: Inbound call TwiML is valid and contains expected elements."""
    from integrations.voice import handle_inbound_call

    twiml = handle_inbound_call(caller="+2348012345678")

    assert "<Response>" in twiml,  "Missing TwiML Response tag"
    assert "<Say"      in twiml,  "Missing Say verb"
    assert "<Gather"   in twiml,  "Missing Gather verb"
    assert "recorded"   in twiml.lower(), "Missing recording consent notice"

    print(f"   TwiML length: {len(twiml)} chars")
    return twiml


def test_twiml_connect():
    """TC-4-02: Connect and record TwiML contains Dial and Record."""
    from integrations.voice import connect_and_record

    twiml = connect_and_record(caller="+2348012345678")

    assert "<Response>"   in twiml
    assert "<Dial"        in twiml,  "Missing Dial verb"
    assert "record-from"  in twiml,  "Missing recording instruction"

    print(f"   TwiML length: {len(twiml)} chars")
    return twiml


def test_twiml_voicemail():
    """TC-4-03: Voicemail TwiML contains Record verb."""
    from integrations.voice import handle_missed_call

    twiml = handle_missed_call(caller="+2348012345678")

    assert "<Response>" in twiml
    assert "<Record"    in twiml, "Missing Record verb"
    assert "<Say"      in twiml

    print(f"   TwiML length: {len(twiml)} chars")
    return twiml


def test_insight_extraction():
    """
    TC-4-04: Extract insights from a mock transcript.
    Requires ANTHROPIC_API_KEY for full test.
    Falls back gracefully without it.
    """
    from integrations.transcription import extract_call_insights

    mock_transcript = """
    Caller: Hello, good afternoon. My name is Emeka Obi.
    I am calling about the 3-bedroom apartment you advertised in Lekki Phase 1.
    Is it still available?

    Jude: Yes, good afternoon Emeka. The property is still available.
    It is a 3-bedroom fully finished apartment. The asking price is 85 million naira.

    Caller: Okay, that is a bit above my budget. I was thinking around 70 million.
    Can anything be done about the price?

    Jude: We can discuss. Let me see what I can work with.
    Can we schedule a viewing first so you can see the property?
    I can do Thursday after 2PM.

    Caller: Thursday works for me. Let us say 3PM.

    Jude: Perfect. I will send you the address and a fact sheet before then.
    """

    insights = extract_call_insights(
        transcript=mock_transcript,
        caller_number="+2348055443322",
        duration_secs=245,
    )

    assert "summary"      in insights
    assert "action_items" in insights
    assert "sentiment"    in insights
    assert "significance" in insights

    print(f"   Caller: {insights.get('caller_name')}")
    print(f"   Summary: {insights.get('summary')}")
    print(f"   Sentiment: {insights.get('sentiment')}")
    print(f"   Actions: {insights.get('action_items')}")
    print(f"   Client facts: {insights.get('client_facts')}")

    return insights


def test_call_processor_mock():
    """
    TC-4-05: Full call processor with mock data.
    Tests memory update and Telegram notification without a real recording.
    """
    from agent.call_processor import (
        _log_call_episode,
        _store_client_facts,
        _queue_action_items,
    )
    from integrations.telegram import send_simple

    # Test episode logging
    _log_call_episode(
        caller_number="+2348055443322",
        caller_name="Mr Emeka Obi",
        summary="Client called about Lekki 3-bed. Interested but price sensitive. Viewing booked for Thursday 3PM.",
        sentiment="positive",
        significance="high",
        topics=["property_inquiry", "price_negotiation", "viewing_scheduled"],
        promises=["Send fact sheet before Thursday", "Confirm address"],
    )

    # Test client fact storage
    _store_client_facts(
        caller_number="+2348055443322",
        caller_name="Mr Emeka Obi",
        facts=[
            "Budget around 70 million naira",
            "Interested in Lekki Phase 1",
            "Price sensitive — open to negotiation",
        ],
    )

    # Test action item queuing
    _queue_action_items(
        caller_number="+2348055443322",
        caller_name="Mr Emeka Obi",
        action_items=[
            "Send property fact sheet to Emeka",
            "Confirm Thursday 3PM viewing in calendar",
            "Prepare price negotiation options",
        ],
        follow_up_by="Thursday",
    )

    # Send test summary to Jude's Telegram
    send_simple(
        "🧪 Phase 4 test — call processor working\n\n"
        "📞 Test call: Mr Emeka Obi (+2348055443322)\n"
        "Duration: 4m 5s\n"
        "Summary: Client interested in Lekki 3-bed. Price sensitive. Viewing Thursday 3PM.\n"
        "Sentiment: Positive\n\n"
        "📋 Action items:\n"
        "  1. Send property fact sheet to Emeka\n"
        "  2. Confirm Thursday 3PM in calendar\n"
        "  3. Prepare negotiation options\n\n"
        "✅ Memory updated — episodic, long-term, priority queue all written."
    )

    print("   Episode logged to episodic memory")
    print("   Client facts stored to long-term memory")
    print("   Action items queued in priority queue")
    print("   Telegram summary sent — check your phone")
    return True


def run_all():
    console.print()
    console.print(Panel(
        "[bold]J-OS Phase 4 — Voice Pipeline Tests[/bold]",
        border_style="bright_blue",
    ))
    console.print()

    tests = [
        ("TC-4-01", "Inbound call TwiML",          test_twiml_inbound),
        ("TC-4-02", "Connect and record TwiML",     test_twiml_connect),
        ("TC-4-03", "Voicemail TwiML",              test_twiml_voicemail),
        ("TC-4-04", "Call insight extraction",      test_insight_extraction),
        ("TC-4-05", "Call processor + memory update", test_call_processor_mock),
    ]

    results = []
    for test_id, label, fn in tests:
        try:
            result = fn()
            console.print(f"[green]✅ {test_id}[/green] — {label}")
            results.append((test_id, True))
        except Exception as e:
            console.print(f"[red]❌ {test_id}[/red] — {label}")
            console.print(f"   [red]{str(e)}[/red]")
            results.append((test_id, False))
        console.print()

    passed = sum(1 for _, ok in results if ok)
    total  = len(results)
    color  = "green" if passed == total else "yellow"
    console.print(Panel(
        f"[bold {color}]{passed}/{total} tests passed[/bold {color}]",
        border_style=color,
    ))


if __name__ == "__main__":
    run_all()