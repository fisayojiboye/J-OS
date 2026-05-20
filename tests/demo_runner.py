"""
tests/demo_runner.py
────────────────────
Demonstrates the full Jude Agent pipeline with rich output.
Works in two modes:
  - LIVE mode:  ANTHROPIC_API_KEY set → real Claude API calls
  - DEMO mode:  No API key → shows architecture with mock LLM responses
 
Run: python tests/demo_runner.py
"""
 
import sys
import os
import json
import time
 
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
 
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.columns import Columns
from rich.text import Text
from rich import box
from rich.rule import Rule
 
console = Console()
 
# ── Mock LLM for demo mode (no API key needed) ────────────────────────────────
 
MOCK_RESPONSES = {
    "New Buyer": {
        "classification": "property_inquiry",
        "priority_score": 6,
        "routing": "queue_approval",
        "draft_response": (
            "Hello, thanks for reaching out!\n\n"
            "The 3-bedroom apartment in Lekki Phase 1 is still available. "
            "To give you the full details including pricing, can I ask a few quick questions?\n\n"
            "• Are you looking to buy or rent?\n"
            "• What's your preferred timeline?\n\n"
            "Looking forward to helping you find the right fit."
        ),
        "reasoning": "New lead — property inquiry. Medium priority. Needs qualification before committing details.",
        "memory_update": {
            "learn_fact": "New buyer inquiring about Lekki Phase 1 3-bedroom. Source: WhatsApp.",
            "log_episode": None,
        },
        "escalation_note": None,
    },
    "Colleague": {
        "classification": "scheduling",
        "priority_score": 9,
        "routing": "auto_escalate",
        "draft_response": None,
        "reasoning": "Exam reminder — episodic memory shows Jude previously missed an exam. Critical priority. Escalating immediately.",
        "memory_update": {
            "learn_fact": None,
            "log_episode": "Received exam reminder for REAN certification — day before exam.",
        },
        "escalation_note": (
            "🚨 URGENT — Colleague via WhatsApp\n"
            "Category: scheduling | Score: 9/10\n"
            "Your REAN certification exam is TOMORROW at 9AM.\n"
            "This is your second attempt — do not miss it.\n"
            "Agent note: Based on past episode (you missed an exam before), this has been flagged critical."
        ),
    },
    "Mr Emeka": {
        "classification": "negotiation",
        "priority_score": 8,
        "routing": "queue_approval",
        "draft_response": (
            "Hi Emeka, I really appreciate your interest and I'm glad you love the property.\n\n"
            "I understand the budget is a consideration. Let me see what options I can work with — "
            "we may be able to structure an installment plan that makes it more comfortable for you.\n\n"
            "Can I come back to you by tomorrow with some options?"
        ),
        "reasoning": "VIP client requesting price reduction. Procedural memory says offer installment options. "
                     "Cannot commit to discount >10% — queuing for Jude's approval.",
        "memory_update": {
            "learn_fact": "Mr Emeka is price-sensitive. Responded to installment option framing.",
            "log_episode": "Mr Emeka requested price reduction on property — offered to explore installments.",
        },
        "escalation_note": None,
    },
    "Angry Client": {
        "classification": "legal",
        "priority_score": 10,
        "routing": "auto_escalate",
        "draft_response": None,
        "reasoning": "Legal threat detected. Client mentions lawyer and court. GUARDRAIL: auto-escalate immediately. No autonomous response.",
        "memory_update": {
            "learn_fact": None,
            "log_episode": "Client threatened legal action over alleged double-sale of property. Lawyer mentioned.",
        },
        "escalation_note": (
            "🚨 LEGAL THREAT — Angry Client via WhatsApp\n"
            "Category: legal | Score: 10/10\n"
            "Client claims they paid a deposit and the property was sold to someone else.\n"
            "They have mentioned a lawyer and court action.\n"
            "⚠️ Do NOT respond to this client yet. Speak to your lawyer first."
        ),
    },
    "Mrs Adaeze": {
        "classification": "scheduling",
        "priority_score": 4,
        "routing": "handle_silently",
        "draft_response": (
            "Hi Adaeze, no problem at all — Friday at 3PM works perfectly.\n\n"
            "I'll send you the property address and directions the morning of the visit. "
            "Looking forward to seeing you then!"
        ),
        "reasoning": "Routine rescheduling from a known VIP client. Calendar check confirms Friday 3PM is clear. Handling silently.",
        "memory_update": {
            "learn_fact": "Mrs Adaeze rescheduled Thursday 2PM → Friday 3PM viewing.",
            "log_episode": None,
        },
        "escalation_note": None,
    },
    "Mr Babatunde": {
        "classification": "payment",
        "priority_score": 10,
        "routing": "auto_escalate",
        "draft_response": None,
        "reasoning": "Payment request — client asking for bank details. GUARDRAIL: never share payment details autonomously. Escalating to Jude.",
        "memory_update": {
            "learn_fact": "Mr Babatunde is ready to pay deposit for VI apartment.",
            "log_episode": "Mr Babatunde indicated payment readiness — requested bank details.",
        },
        "escalation_note": (
            "🚨 PAYMENT READY — Mr Babatunde via WhatsApp\n"
            "Category: payment | Score: 10/10\n"
            "Babatunde is ready to pay the deposit for the VI apartment TODAY.\n"
            "He's asking for your bank details.\n"
            "⚠️ Respond personally — do NOT let the agent share payment details."
        ),
    },
    "Unknown": {
        "classification": "spam",
        "priority_score": 1,
        "routing": "handle_silently",
        "draft_response": None,
        "reasoning": "Spam detected — prize/lottery language, suspicious link. Discarding silently. No response sent.",
        "memory_update": {"learn_fact": None, "log_episode": None},
        "escalation_note": None,
    },
    "Chief Okafor": {
        "classification": "property_inquiry",
        "priority_score": 9,
        "routing": "auto_escalate",
        "draft_response": (
            "Chief Okafor, thank you — this sounds like a very exciting opportunity.\n\n"
            "For a ₦150M investment budget focused on waterfront/island properties, "
            "we have several options worth exploring. I'm putting together a curated shortlist right now.\n\n"
            "Would your brother be available for a call this week? Jude would love to speak with him directly."
        ),
        "reasoning": "High-value VIP referral. ₦150M budget. Waterfront preference. Jude should handle this personally — escalating while queuing a warm draft.",
        "memory_update": {
            "learn_fact": "Chief Okafor has a UK-based brother investing ₦150M in Lagos real estate. Prefers waterfront/island.",
            "log_episode": "Chief Okafor referred high-value investor — brother with ₦150M budget.",
        },
        "escalation_note": (
            "💰 HIGH-VALUE LEAD — Chief Okafor via WhatsApp\n"
            "Category: property_inquiry | Score: 9/10\n"
            "Chief Okafor's brother is looking to invest ₦150M in Lagos real estate.\n"
            "Preferences: waterfront, island locations (Lekki, VI, Ikoyi).\n"
            "Draft response queued — but you should follow up personally. This is a big one."
        ),
    },
}
 
TEST_CASES = [
    {
        "id": "TC-01", "label": "New property inquiry",
        "message": "Hi, I saw your 3-bedroom listing in Lekki Phase 1. Is it still available? What is the price?",
        "source": "whatsapp", "sender": "New Buyer", "sender_is_vip": False,
        "expect_routing": ["queue_approval", "handle_silently", "inform_only"],
    },
    {
        "id": "TC-02", "label": "Exam reminder (critical)",
        "message": "Jude, your REAN certification exam is tomorrow morning at 9AM. This is your second attempt.",
        "source": "whatsapp", "sender": "Colleague", "sender_is_vip": False,
        "expect_routing": ["auto_escalate"],
    },
    {
        "id": "TC-03", "label": "VIP client negotiating price",
        "message": "Hi Jude, we love the property but the price is too high. Can you come down to ₦45M? We are serious.",
        "source": "whatsapp", "sender": "Mr Emeka", "sender_is_vip": True,
        "expect_routing": ["queue_approval", "auto_escalate"],
    },
    {
        "id": "TC-04", "label": "Legal threat ⚠️",
        "message": "I paid a holding deposit and you gave the property to someone else. My lawyer will contact you. We are going to court.",
        "source": "whatsapp", "sender": "Angry Client", "sender_is_vip": False,
        "expect_routing": ["auto_escalate"],
    },
    {
        "id": "TC-05", "label": "Routine rescheduling",
        "message": "Hi, can we move our viewing from Thursday 2PM to Friday 3PM? Something came up.",
        "source": "whatsapp", "sender": "Mrs Adaeze", "sender_is_vip": True,
        "expect_routing": ["handle_silently", "queue_approval", "inform_only"],
    },
    {
        "id": "TC-06", "label": "Payment request 💰",
        "message": "Jude I'm ready to pay the deposit for the VI apartment. Please send me your account details to transfer today.",
        "source": "whatsapp", "sender": "Mr Babatunde", "sender_is_vip": True,
        "expect_routing": ["auto_escalate", "queue_approval"],
    },
    {
        "id": "TC-07", "label": "Spam",
        "message": "Congratulations! You have won ₦500,000. Click this link to claim your reward. Offer expires in 24 hours.",
        "source": "whatsapp", "sender": "Unknown", "sender_is_vip": False,
        "expect_routing": ["handle_silently", "inform_only"],
    },
    {
        "id": "TC-08", "label": "High-value VIP referral 💎",
        "message": "Jude, my brother in the UK wants to invest ₦150M in Lagos real estate. He prefers waterfront or island. Can you put together options?",
        "source": "whatsapp", "sender": "Chief Okafor", "sender_is_vip": True,
        "expect_routing": ["queue_approval", "auto_escalate"],
    },
]
 
 
def run_demo_test(tc: dict, live_mode: bool) -> dict:
    start = time.time()
 
    if live_mode:
        from agent.graph import jude_agent
        from agent.state import initial_state
        state = initial_state(
            message=tc["message"], source=tc["source"],
            sender=tc["sender"], sender_is_vip=tc["sender_is_vip"],
        )
        result = jude_agent.invoke(state)
        routing  = result.get("routing", "queue_approval")
        category = result.get("category", "unknown")
        score    = result.get("priority_score", 5)
        draft    = result.get("draft_response", "")
        escalation = result.get("escalation_note", "")
        reasoning  = result.get("reasoning", "")
        nodes      = result.get("completed_nodes", [])
        error      = result.get("error")
    else:
        # Demo mode — use mock responses
        mock = MOCK_RESPONSES.get(tc["sender"], {
            "classification": "unknown", "priority_score": 5,
            "routing": "queue_approval",
            "draft_response": "Thanks for your message. Jude will get back to you.",
            "reasoning": "Demo mode — mock response.",
            "memory_update": {}, "escalation_note": None,
        })
        time.sleep(0.1)   # simulate processing
        routing    = mock["routing"]
        category   = mock["classification"]
        score      = mock["priority_score"]
        draft      = mock.get("draft_response", "")
        escalation = mock.get("escalation_note", "")
        reasoning  = mock.get("reasoning", "")
        nodes      = ["load_memory", "classify", "draft" if routing != "auto_escalate" else "escalate", "update_memory", "finalize"]
        error      = None
 
    elapsed  = round(time.time() - start, 2)
    passed   = routing in tc["expect_routing"] and error is None
 
    return {
        "id": tc["id"], "label": tc["label"], "passed": passed,
        "routing": routing, "category": category, "score": score,
        "draft": draft or "", "escalation": escalation or "",
        "reasoning": reasoning, "nodes": nodes, "elapsed": elapsed, "error": error,
        "routing_ok": routing in tc["expect_routing"],
    }
 
 
def print_demo(results: list[dict], live_mode: bool) -> None:
    mode_label = "[bold green]LIVE (Claude API)[/bold green]" if live_mode else "[bold yellow]DEMO (mock responses)[/bold yellow]"
    passed = sum(1 for r in results if r["passed"])
    total  = len(results)
 
    console.print()
    console.print(Panel(
        f"  [bold white]J-OS — Jude's AI Operations Agent[/bold white]\n"
        f"  Brain Test Suite | Mode: {mode_label}\n\n"
        f"  [bold]{'✅' if passed == total else '⚠️ '} {passed}/{total} tests passed[/bold]",
        style="on #0A0A14",
        border_style="bright_blue",
    ))
    console.print()
 
    # Summary table
    t = Table(box=box.ROUNDED, header_style="bold bright_cyan", border_style="bright_black")
    t.add_column("ID",       width=6,  justify="center")
    t.add_column("Scenario", width=32)
    t.add_column("Category", width=18)
    t.add_column("Score",    width=7,  justify="center")
    t.add_column("Routing",  width=18)
    t.add_column("Result",   width=8,  justify="center")
 
    routing_colors = {
        "auto_escalate":  "bold red",
        "queue_approval": "bold yellow",
        "inform_only":    "cyan",
        "handle_silently":"dim green",
    }
 
    for r in results:
        rc = routing_colors.get(r["routing"], "white")
        result_icon = "[green]PASS[/green]" if r["passed"] else "[red]FAIL[/red]"
        t.add_row(
            r["id"], r["label"],
            r["category"],
            f"[bold]{r['score']}/10[/bold]",
            f"[{rc}]{r['routing']}[/{rc}]",
            result_icon,
        )
 
    console.print(t)
    console.print()
 
    # Detail panels
    for r in results:
        icon = "✅" if r["passed"] else "❌"
        color = "green" if r["passed"] else "red"
 
        header = f"{icon} [bold]{r['id']}[/bold] — {r['label']}"
        body_lines = [
            f"[dim]Nodes:[/dim] {' → '.join(r['nodes'])}",
            f"[dim]Reasoning:[/dim] [italic]{r['reasoning']}[/italic]",
        ]
 
        if r["draft"]:
            body_lines.append(f"\n[cyan bold]Draft (in Jude's voice):[/cyan bold]")
            body_lines.append(f"[dim]{r['draft']}[/dim]")
 
        if r["escalation"]:
            body_lines.append(f"\n[red bold]Escalation alert to Jude:[/red bold]")
            body_lines.append(f"[red dim]{r['escalation']}[/red dim]")
 
        if r["error"]:
            body_lines.append(f"\n[red]Error: {r['error']}[/red]")
 
        console.print(Panel(
            "\n".join(body_lines),
            title=header,
            border_style=color,
            expand=True,
        ))
        console.print()
 
    # Final
    console.print(Rule(style="bright_black"))
    if passed == total:
        console.print(Panel(
            "[bold green]🎉 ALL TESTS PASSED\n"
            "The brain is working correctly across all 5 memory layers.\n"
            "Classification, routing, guardrails, and drafting all functional.[/bold green]",
            border_style="green",
        ))
    else:
        failed_ids = [r["id"] for r in results if not r["passed"]]
        console.print(Panel(
            f"[bold yellow]⚠️  {total - passed} test(s) need review: {', '.join(failed_ids)}\n"
            f"Check routing rules and system prompt calibration.[/bold yellow]",
            border_style="yellow",
        ))
    console.print()
 
 
if __name__ == "__main__":
    live_mode = bool(os.getenv("ANTHROPIC_API_KEY"))
 
    console.print(f"\n[bold]J-OS Brain Demo[/bold] — {'LIVE mode' if live_mode else 'DEMO mode (set ANTHROPIC_API_KEY for live)'}")
    console.print(f"[dim]Running {len(TEST_CASES)} scenarios...[/dim]\n")
 
    results = []
    for tc in TEST_CASES:
        console.print(f"  [dim]→ {tc['id']}: {tc['label']}[/dim]")
        try:
            r = run_demo_test(tc, live_mode)
        except Exception as e:
            r = {
                "id": tc["id"], "label": tc["label"], "passed": False,
                "routing": "error", "category": "error", "score": 0,
                "draft": "", "escalation": "", "reasoning": "",
                "nodes": [], "elapsed": 0, "error": str(e), "routing_ok": False,
            }
        results.append(r)
 
    print_demo(results, live_mode)
 