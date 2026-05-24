"""
agent/call_processor.py
────────────────────────
Processes completed calls and updates all memory layers.

This is the bridge between the transcription pipeline
and the agent's 5-layer memory system.

After every call:
  - Episodic memory  ← logs what happened
  - Long-term memory ← stores new client facts
  - Priority queue   ← adds action items
  - Telegram         ← sends Jude the summary
"""

import time
from agent.memory.manager import MemoryManager
from integrations.telegram import send_simple, send_alert
from integrations.transcription import transcribe_recording, extract_call_insights
from integrations.voice import get_call_details


memory = MemoryManager(seed=False)


def process_completed_call(
    recording_url: str,
    caller_number: str,
    call_sid:      str,
    call_type:     str = "inbound",   # "inbound" | "voicemail" | "screening"
) -> dict:
    """
    Full post-call processing pipeline.

    Called by the webhook when Twilio confirms a recording is ready.
    Runs the complete pipeline:
      transcribe → extract insights → update memory → notify Jude

    Args:
        recording_url: Twilio MP3 URL
        caller_number: Who called
        call_sid:      Twilio call identifier
        call_type:     Type of recording

    Returns:
        Processing result dict
    """

    # ── Step 1: Notify Jude processing has started ────────────────────────────
    send_simple(
        f"📞 Processing call from {caller_number}...\n"
        f"Transcribing recording now."
    )

    # ── Step 2: Fetch call metadata from Twilio ───────────────────────────────
    call_details  = get_call_details(call_sid) if call_sid else {}
    duration_secs = int(call_details.get("duration", 0))

    # ── Step 3: Transcribe the recording ─────────────────────────────────────
    transcription = transcribe_recording(recording_url)

    if not transcription["success"]:
        error_msg = transcription.get("error", "Unknown error")
        send_simple(
            f"⚠️ Transcription failed for call from {caller_number}\n"
            f"Error: {error_msg}\n"
            f"Recording URL saved for manual review."
        )
        # Still log it happened even if transcription failed
        _log_call_episode(
            caller_number=caller_number,
            summary="Transcription failed — call recorded but not analyzed",
            significance="low",
        )
        return {"success": False, "error": error_msg}

    transcript = transcription["transcript"]

    # ── Step 4: Extract insights with Claude ──────────────────────────────────
    insights = extract_call_insights(
        transcript=transcript,
        caller_number=caller_number,
        duration_secs=duration_secs,
    )

    # ── Step 5: Update episodic memory ───────────────────────────────────────
    _log_call_episode(
        caller_number=caller_number,
        caller_name=insights.get("caller_name"),
        summary=insights.get("summary", ""),
        sentiment=insights.get("sentiment", "neutral"),
        significance=insights.get("significance", "medium"),
        topics=insights.get("topics", []),
        promises=insights.get("promises_made", []),
    )

    # ── Step 6: Update long-term memory with new client facts ─────────────────
    client_facts = insights.get("client_facts", [])
    if client_facts:
        _store_client_facts(
            caller_number=caller_number,
            caller_name=insights.get("caller_name"),
            facts=client_facts,
        )

    # ── Step 7: Add action items to priority queue ────────────────────────────
    action_items = insights.get("action_items", [])
    if action_items:
        _queue_action_items(
            caller_number=caller_number,
            caller_name=insights.get("caller_name"),
            action_items=action_items,
            follow_up_by=insights.get("follow_up_by"),
        )

    # ── Step 8: Send Jude the Telegram summary ────────────────────────────────
    telegram_summary = insights.get("telegram_summary", "")
    if not telegram_summary:
        duration_str     = f"{duration_secs // 60}m {duration_secs % 60}s"
        telegram_summary = (
            f"📞 Call from {caller_number}\n"
            f"Duration: {duration_str}\n"
            f"Summary: {insights.get('summary', 'No summary available')}"
        )

    # Add action items to the Telegram message
    if action_items:
        telegram_summary += "\n\n📋 Action items:"
        for i, item in enumerate(action_items, 1):
            telegram_summary += f"\n  {i}. {item}"

    # Add promises if any
    promises = insights.get("promises_made", [])
    if promises:
        telegram_summary += "\n\n🤝 Promises made:"
        for p in promises:
            telegram_summary += f"\n  • {p}"

    send_simple(telegram_summary)

    return {
        "success":     True,
        "caller":      caller_number,
        "transcript":  transcript,
        "insights":    insights,
        "actions":     action_items,
    }


def _log_call_episode(
    caller_number: str,
    summary:       str,
    significance:  str      = "medium",
    caller_name:   str      = None,
    sentiment:     str      = "neutral",
    topics:        list     = None,
    promises:      list     = None,
) -> None:
    """Write call to episodic memory."""
    who    = caller_name or caller_number
    topics = topics   or []
    promises = promises or []

    what = summary
    if promises:
        what += f" Promises made: {', '.join(promises)}."

    # Map sentiment to outcome
    outcome_map = {
        "positive": "positive",
        "negative": "negative",
        "neutral":  "neutral",
    }

    memory.episodic.record(
        title=f"Phone call with {who}",
        what=what,
        who=who,
        outcome=outcome_map.get(sentiment, "neutral"),
        significance=significance,
        lesson="",
        tags=["phone_call"] + topics,
        context={
            "caller_number": caller_number,
            "sentiment":     sentiment,
            "topics":        topics,
        },
    )


def _store_client_facts(
    caller_number: str,
    facts:         list,
    caller_name:   str = None,
) -> None:
    """Store new facts about a client in long-term memory."""
    identifier = caller_name or caller_number
    key_prefix = identifier.lower().replace(" ", "_").replace("+", "")

    for i, fact in enumerate(facts):
        key = f"{key_prefix}_fact_{int(time.time())}_{i}"
        memory.long_term.set(
            key=key,
            value=fact,
            namespace="clients",
            tags=["from_call", caller_number],
            source="agent_learned",
        )


def _queue_action_items(
    caller_number: str,
    action_items:  list,
    caller_name:   str = None,
    follow_up_by:  str = None,
) -> None:
    """Add action items to the priority queue."""
    identifier = caller_name or caller_number

    for item in action_items:
        # Action items from calls are always high priority
        body = f"Action from call with {identifier}: {item}"
        if follow_up_by:
            body += f" (by {follow_up_by})"

        memory.priority.enqueue(
            title=f"Action: {item[:50]}",
            body=body,
            source="call",
            sender=identifier,
            metadata={"is_vip": False},
            tags=["action_item", "from_call"],
        )