from langgraph.graph import StateGraph, END
from agent.state import AgentState
from agent.nodes import (
    node_load_memory,
    node_classify,
    node_calendar_check,
    node_draft_response,
    node_escalate,
    node_update_memory,
    node_finalize,
    route_after_classify,
)

def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("load_memory",    node_load_memory)
    graph.add_node("classify",       node_classify)
    graph.add_node("calendar_check", node_calendar_check)
    graph.add_node("draft",          node_draft_response)
    graph.add_node("escalate",       node_escalate)
    graph.add_node("update_memory",  node_update_memory)
    graph.add_node("finalize",       node_finalize)

    graph.set_entry_point("load_memory")
    graph.add_edge("load_memory", "classify")

    graph.add_conditional_edges(
        "classify",
        route_after_classify,
        {
            "draft":    "draft",
            "escalate": "escalate",
            "calendar": "calendar_check",
        },
    )

    graph.add_edge("calendar_check", "draft")
    graph.add_edge("draft",          "update_memory")
    graph.add_edge("escalate",       "update_memory")
    graph.add_edge("update_memory",  "finalize")
    graph.add_edge("finalize",       END)

    return graph.compile()

jude_agent = build_graph()
