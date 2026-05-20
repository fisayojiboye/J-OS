"""
agent/state.py
──────────────
The AgentState is the shared data object that flows through every node
in the LangGraph graph. Every node reads from it and writes to it.
"""
 
from typing import TypedDict, Literal, Optional
 
 
class AgentState(TypedDict):
    # INPUT
    message:          str
    source:           str
    sender:           str
    sender_is_vip:    bool
    thread_id:        str
    # MEMORY CONTEXT
    memory_block:     str
    client_context:   str
    # CLASSIFICATION
    category:         str
    priority_score:   int
    routing:          str
    keywords_hit:     list
    # RESPONSE
    draft_response:   Optional[str]
    escalation_note:  Optional[str]
    reasoning:        str
    # MEMORY UPDATES
    learn_fact:       Optional[str]
    log_episode:      Optional[str]
    # PIPELINE STATUS
    error:            Optional[str]
    completed_nodes:  list
    final_action:     Optional[str]
 
 
def initial_state(
    message: str,
    source:  str  = "whatsapp",
    sender:  str  = "unknown",
    sender_is_vip: bool = False,
    thread_id:     str  = "default",
) -> AgentState:
    return AgentState(
        message=message,
        source=source,
        sender=sender,
        sender_is_vip=sender_is_vip,
        thread_id=thread_id,
        memory_block="",
        client_context="",
        category="unknown",
        priority_score=5,
        routing="queue_approval",
        keywords_hit=[],
        draft_response=None,
        escalation_note=None,
        reasoning="",
        learn_fact=None,
        log_episode=None,
        error=None,
        completed_nodes=[],
        final_action=None,
    )
 