from typing import TypedDict, Optional

class AgentState(TypedDict):
    message:          str
    source:           str
    sender:           str
    sender_is_vip:    bool
    thread_id:        str
    memory_block:     str
    client_context:   str
    category:         str
    priority_score:   int
    routing:          str
    keywords_hit:     list
    draft_response:   Optional[str]
    escalation_note:  Optional[str]
    reasoning:        str
    learn_fact:       Optional[str]
    log_episode:      Optional[str]
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
        message=message, source=source, sender=sender,
        sender_is_vip=sender_is_vip, thread_id=thread_id,
        memory_block="", client_context="",
        category="unknown", priority_score=5,
        routing="queue_approval", keywords_hit=[],
        draft_response=None, escalation_note=None,
        reasoning="", learn_fact=None, log_episode=None,
        error=None, completed_nodes=[], final_action=None,
    )
