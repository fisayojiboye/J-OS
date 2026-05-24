"""
agent/nodes.py — LangGraph nodes for the Jude Agent pipeline.
 
Flow: load_memory → classify → route → [draft | escalate] → update_memory → finalize
"""
 
import json
import time
import re
import anthropic
from pathlib import Path
from config.settings import ANTHROPIC_API_KEY, CLAUDE_MODEL, MAX_TOKENS
from agent.state import AgentState
from agent.prompt import build_system_prompt
from agent.memory.manager import MemoryManager
 
memory = MemoryManager(seed=True)
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
 
 
def node_load_memory(state: AgentState) -> dict:
    """Pull all memory layers into context block."""
    memory.short_term.add_turn("user", state["message"], source=state["source"])
    metadata = {"is_vip": state.get("sender_is_vip", False)}
    score_data = memory.priority.score_message(
        state["message"], source=state["source"],
        sender=state["sender"], metadata=metadata,
    )
    memory_block   = memory.build_context_block(person=state["sender"])
    client_context = memory.get_client_context(state["sender"])
    return {
        "memory_block":    memory_block,
        "client_context":  client_context,
        "priority_score":  score_data["score"],
        "keywords_hit":    score_data["keywords_hit"],
        "completed_nodes": state.get("completed_nodes", []) + ["load_memory"],
    }
 
 
def node_calendar_check(state: AgentState) -> dict:
    """
    Runs when category == "scheduling".
    Checks Jude's actual calendar and enriches the state
    with real availability data before drafting a response.

    This node turns a generic scheduling reply into one that
    actually says "Jude is free Thursday at 2PM" instead of
    "I'll check and get back to you."
    """
    from integrations.calendar import CalendarService

    # Only run this if calendar credentials exist
    # If credentials.json isn't there yet, skip gracefully
    from pathlib import Path
    if not Path("credentials.json").exists() and not Path("token.json").exists():
        return {
            "completed_nodes": state.get("completed_nodes", []) + ["calendar_skip"],
        }

    try:
        cal = CalendarService()

        # Get today's events to give the agent real context
        todays_events = cal.get_todays_events()
        upcoming      = cal.get_upcoming_events(days=3)

        # Format for injection into the draft context
        schedule_context = "Jude's current schedule:\n"

        if todays_events:
            schedule_context += "Today:\n"
            for e in todays_events:
                schedule_context += f"  • {e['start_time']} — {e['title']}\n"
        else:
            schedule_context += "Today: Calendar is clear.\n"

        if upcoming:
            schedule_context += "Next 3 days:\n"
            for e in upcoming[:5]:   # Max 5 to keep context clean
                schedule_context += f"  • {e['start_date']} {e['start_time']} — {e['title']}\n"

        # Store in short-term memory so the draft node can use it
        memory.short_term.set_context("schedule_context", schedule_context)

        return {
            "completed_nodes": state.get("completed_nodes", []) + ["calendar_check"],
        }

    except Exception as e:
        # Calendar failure should NEVER crash the agent
        # Just log and continue — draft node will fall back to generic
        memory.short_term.set_context("schedule_context", f"Calendar unavailable: {str(e)}")
        return {
            "completed_nodes": state.get("completed_nodes", []) + ["calendar_error"],
        }
    

def node_classify(state: AgentState) -> dict:
    """Claude classifies, scores, routes, and drafts in one call."""
    system_prompt = build_system_prompt(
        memory_context=state.get("memory_block", ""),
        task_context=(
            f"Sender: {state['sender']} | Source: {state['source']} | "
            f"Client context: {state.get('client_context', 'No prior context')}"
        ),
    )
    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": (
                    f"New incoming message from {state['sender']} via {state['source']}:\n\n"
                    f"\"{state['message']}\"\n\n"
                    f"Heuristic priority score: {state['priority_score']}/10\n"
                    f"Keywords detected: {', '.join(state['keywords_hit']) or 'none'}\n\n"
                    "Classify, score, route, and draft. Return only the JSON object."
                ),
            }],
        )
        raw = response.content[0].text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        parsed = json.loads(raw)
        return {
            "category":        parsed.get("classification", "unknown"),
            "priority_score":  parsed.get("priority_score", state["priority_score"]),
            "routing":         parsed.get("routing", "queue_approval"),
            "draft_response":  parsed.get("draft_response"),
            "escalation_note": parsed.get("escalation_note"),
            "reasoning":       parsed.get("reasoning", ""),
            "learn_fact":      parsed.get("memory_update", {}).get("learn_fact"),
            "log_episode":     parsed.get("memory_update", {}).get("log_episode"),
            "completed_nodes": state.get("completed_nodes", []) + ["classify"],
        }
    except (json.JSONDecodeError, anthropic.APIError, Exception) as e:
        return {
            "error":           f"Classification error: {str(e)}",
            "routing":         "queue_approval",
            "reasoning":       "Error during classification — defaulting to queue for safety.",
            "completed_nodes": state.get("completed_nodes", []) + ["classify_error"],
        }
 
 
def node_draft_response(state: AgentState) -> dict:
    """Validate/store the draft. Log the action."""
    draft = state.get("draft_response") or "Thanks for your message. Jude will get back to you shortly."
    memory.short_term.add_turn("assistant", draft)
    memory.short_term.log_action(
        action="draft_response",
        result=f"Drafted response for {state['sender']}",
        metadata={"routing": state["routing"], "category": state["category"]},
    )
    return {
        "draft_response":  draft,
        "final_action":    f"Draft queued ({state['routing']})",
        "completed_nodes": state.get("completed_nodes", []) + ["draft_response"],
    }
 
 
def node_escalate(state: AgentState) -> dict:
    """Compose urgent Jude alert. No draft sent."""
    alert = (
        f"🚨 URGENT — {state['sender']} via {state['source']}\n"
        f"Category: {state['category']} | Score: {state['priority_score']}/10\n"
        f"Message: {state['message'][:200]}\n"
        f"Reason: {state.get('reasoning', 'High priority detected')}"
    )
    if state.get("escalation_note"):
        alert += f"\nAgent note: {state['escalation_note']}"
    memory.short_term.log_action(
        "escalate_to_jude", f"Alert for {state['sender']}",
        {"category": state["category"], "score": state["priority_score"]},
    )
    return {
        "final_action":    f"ESCALATED — {state['category']}",
        "escalation_note": alert,
        "draft_response":  None,
        "completed_nodes": state.get("completed_nodes", []) + ["escalate"],
    }
 
 
def node_update_memory(state: AgentState) -> dict:
    """Persist new facts and episodes. Always enqueue in priority system."""
    if state.get("learn_fact"):
        fact_key = f"{state['sender'].lower().replace(' ', '_')}_{int(time.time())}"
        memory.long_term.set(fact_key, state["learn_fact"], namespace="clients", source="agent_learned")
    if state.get("log_episode"):
        memory.episodic.record(
            title=f"Interaction with {state['sender']}",
            what=state["log_episode"],
            who=state["sender"],
            outcome="unknown",
            significance="medium",
            tags=[state["category"], state["source"]],
        )
    memory.priority.enqueue(
        title=f"{state['category']} from {state['sender']}",
        body=state["message"],
        source=state["source"],
        sender=state["sender"],
        metadata={"is_vip": state.get("sender_is_vip", False)},
        tags=[state["category"]],
    )
    return {"completed_nodes": state.get("completed_nodes", []) + ["update_memory"]}
 
 
def node_finalize(state: AgentState) -> dict:
    """Log completed cycle."""
    memory.short_term.log_action(
        "cycle_complete", state.get("final_action", "completed"),
        {"sender": state["sender"], "category": state["category"],
         "routing": state["routing"], "score": state["priority_score"]},
    )
    return {"completed_nodes": state.get("completed_nodes", []) + ["finalize"]}
 
 
def route_after_classify(state: AgentState) -> str:
    """
    Three paths:
      auto_escalate  → escalate node
      scheduling     → calendar_check node first, then draft
      everything else → draft directly
    """
    if state.get("error"):
        return "draft"

    if state.get("routing") == "auto_escalate":
        return "escalate"

    if state.get("category") == "scheduling":
        return "calendar"

    return "draft"

