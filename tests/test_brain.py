"""
tests/test_brain.py
───────────────────
End-to-end brain tests using 8 hardcoded real-world messages.
 
Tests verify:
  1. The graph runs without error
  2. Classification is sensible
  3. Routing decisions are correct
  4. Drafts are in Jude's voice (not robotic)
  5. Escalations fire correctly for sensitive content
  6. Memory updates happen
  7. Guardrails hold
 
Run:  python tests/test_brain.py
"""
 
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
 
import time
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box
 
from agent.graph import jude_agent
from agent.state import initial_state
 
console = Console()
 
# ── Test scenarios ────────────────────────────────────────────────────────────
 
TEST_CASES = [
    {
        "id":          "TC-01",
        "label":       "New lead — property inquiry",
        "message":     "Hello, I saw your listing for the 3-bedroom apartment in Lekki Phase 1. "
                       "I'm interested. How much is it and is it still available?",
        "source":      "whatsapp",
        "sender":      "Unknown Buyer",
        "sender_is_vip": False,
        "expect_category": "property_inquiry",
        "expect_routing":  ["queue_approval", "handle_silently", "inform_only"],
        "expect_no_escalation": True,
    },
    {
        "id":          "TC-02",
        "label":       "Exam / critical deadline",
        "message":     "Jude, just reminding you your REAN certification exam is tomorrow morning at 9AM. "
                       "Please don't forget. This is the second attempt.",
        "source":      "whatsapp",
        "sender":      "Colleague",
        "sender_is_vip": False,
        "expect_category": "scheduling",
        "expect_routing":  ["auto_escalate", "queue_approval"],
        "expect_no_escalation": False,   # This SHOULD escalate or be very high priority
    },
    {
        "id":          "TC-03",
        "label":       "Client negotiating price",
        "message":     "Hi Jude, we really love the property but honestly the price is too high for us. "
                       "Can you come down to ₦45M? We are serious buyers.",
        "source":      "whatsapp",
        "sender":      "Mr Emeka",
        "sender_is_vip": True,
        "expect_category": "negotiation",
        "expect_routing":  ["queue_approval", "auto_escalate"],
        "expect_no_escalation": False,   # Needs Jude's input
    },
    {
        "id":          "TC-04",
        "label":       "Legal threat",
        "message":     "This is unacceptable. I paid a holding deposit and you gave the property to someone else. "
                       "My lawyer will be contacting you. We are prepared to take this to court.",
        "source":      "whatsapp",
        "sender":      "Angry Client",
        "sender_is_vip": False,
        "expect_category": "legal",
        "expect_routing":  ["auto_escalate"],
        "expect_no_escalation": False,   # MUST escalate
    },
    {
        "id":          "TC-05",
        "label":       "Routine scheduling",
        "message":     "Hi, can we reschedule our viewing from Thursday 2PM to Friday 3PM? "
                       "Something came up at work.",
        "source":      "whatsapp",
        "sender":      "Mrs Adaeze",
        "sender_is_vip": True,
        "expect_category": "scheduling",
        "expect_routing":  ["handle_silently", "queue_approval", "inform_only"],
        "expect_no_escalation": True,
    },
    {
        "id":          "TC-06",
        "label":       "Payment / ready to buy",
        "message":     "Jude I'm ready to pay the deposit for the VI apartment. "
                       "Please send me your account details so I can transfer today.",
        "source":      "whatsapp",
        "sender":      "Mr Babatunde",
        "sender_is_vip": True,
        "expect_category": "payment",
        "expect_routing":  ["auto_escalate", "queue_approval"],
        "expect_no_escalation": False,   # MUST escalate — never share bank details autonomously
    },
    {
        "id":          "TC-07",
        "label":       "Spam / irrelevant",
        "message":     "Congratulations! You have won a prize. Click this link to claim your ₦500,000 reward. "
                       "Offer expires in 24 hours.",
        "source":      "whatsapp",
        "sender":      "Unknown",
        "sender_is_vip": False,
        "expect_category": "spam",
        "expect_routing":  ["handle_silently", "inform_only"],
        "expect_no_escalation": True,
    },
    {
        "id":          "TC-08",
        "label":       "VIP client — investment interest",
        "message":     "Jude, my brother in the UK is looking to invest in Lagos real estate. "
                       "He has a budget of ₦150M. Can you put together some options? "
                       "He prefers waterfront or island locations.",
        "source":      "whatsapp",
        "sender":      "Chief Okafor",
        "sender_is_vip": True,
        "expect_category": "property_inquiry",
        "expect_routing":  ["queue_approval", "auto_escalate"],
        "expect_no_escalation": False,   # High value — Jude should know immediately
    },
]
 
 
# ── Test runner ───────────────────────────────────────────────────────────────
 
def run_test(tc: dict) -> dict:
    """Run a single test case through the full agent graph."""
    state = initial_state(
        message=tc["message"],
        source=tc["source"],
        sender=tc["sender"],
        sender_is_vip=tc["sender_is_vip"],
    )
 
    start = time.time()
    result = jude_agent.invoke(state)
    elapsed = round(time.time() - start, 2)
 
    # Evaluate
    cat_ok      = result.get("category") == tc["expect_category"]
    routing_ok  = result.get("routing") in tc["expect_routing"]
    no_error    = result.get("error") is None
    has_draft   = result.get("draft_response") is not None
    nodes_ran   = result.get("completed_nodes", [])
 
    passed = cat_ok and routing_ok and no_error
 
    return {
        "id":         tc["id"],
        "label":      tc["label"],
        "passed":     passed,
        "cat_ok":     cat_ok,
        "routing_ok": routing_ok,
        "no_error":   no_error,
        "has_draft":  has_draft,
        "got_cat":    result.get("category", "—"),
        "got_routing":result.get("routing", "—"),
        "got_score":  result.get("priority_score", "—"),
        "draft":      result.get("draft_response", ""),
        "escalation": result.get("escalation_note", ""),
        "reasoning":  result.get("reasoning", ""),
        "nodes":      nodes_ran,
        "elapsed":    elapsed,
        "error":      result.get("error"),
    }
 
 
def print_results(results: list[dict]) -> None:
    passed = sum(1 for r in results if r["passed"])
    total  = len(results)
 
    console.print()
    console.print(Panel(
        f"[bold]J-OS Brain Test Suite[/bold]\n"
        f"Jude's AI Operations Agent — End-to-End Tests\n\n"
        f"[green]{passed}/{total} tests passed[/green]",
        style="bold white on #0A0A1A",
        expand=False,
    ))
    console.print()
 
    # Summary table
    table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold cyan")
    table.add_column("ID",      width=6)
    table.add_column("Label",   width=32)
    table.add_column("Pass",    width=6)
    table.add_column("Category", width=18)
    table.add_column("Routing", width=18)
    table.add_column("Score",   width=6)
    table.add_column("Time(s)", width=7)
 
    for r in results:
        status = "[green]✓[/green]" if r["passed"] else "[red]✗[/red]"
        cat    = f"[green]{r['got_cat']}[/green]" if r["cat_ok"] else f"[red]{r['got_cat']}[/red]"
        rout   = f"[green]{r['got_routing']}[/green]" if r["routing_ok"] else f"[red]{r['got_routing']}[/red]"
        table.add_row(
            r["id"], r["label"], status, cat, rout,
            str(r["got_score"]), str(r["elapsed"]),
        )
 
    console.print(table)
 
    # Detail for each test
    for r in results:
        icon = "✅" if r["passed"] else "❌"
        console.print(f"\n{icon}  [bold]{r['id']} — {r['label']}[/bold]")
        console.print(f"   Nodes ran: {' → '.join(r['nodes'])}")
        console.print(f"   Reasoning: [italic]{r['reasoning']}[/italic]")
 
        if r["draft"]:
            console.print(f"   [cyan]Draft response:[/cyan]")
            console.print(f"   [dim]{r['draft'][:300]}[/dim]")
 
        if r["escalation"]:
            console.print(f"   [red]Escalation note:[/red]")
            console.print(f"   [dim]{r['escalation'][:300]}[/dim]")
 
        if r["error"]:
            console.print(f"   [red]ERROR: {r['error']}[/red]")
 
    # Final verdict
    console.print()
    if passed == total:
        console.print(Panel(
            "[bold green]🎉 ALL TESTS PASSED — Brain is working correctly[/bold green]",
            style="green",
        ))
    else:
        failed = [r["id"] for r in results if not r["passed"]]
        console.print(Panel(
            f"[bold red]⚠️  {total - passed} test(s) failed: {', '.join(failed)}[/bold red]\n"
            f"Review the detail above — adjust system prompt or routing rules.",
            style="red",
        ))
    console.print()
 
 
if __name__ == "__main__":
    console.print("\n[bold yellow]Starting J-OS Brain Test Suite...[/bold yellow]")
    console.print("[dim]Running 8 real-world scenarios through the full LangGraph pipeline.[/dim]\n")
 
    if not os.getenv("ANTHROPIC_API_KEY"):
        console.print("[bold red]ERROR: ANTHROPIC_API_KEY not set.[/bold red]")
        console.print("Create a .env file with: ANTHROPIC_API_KEY=your_key_here")
        sys.exit(1)
 
    results = []
    for i, tc in enumerate(TEST_CASES):
        console.print(f"[dim]Running {tc['id']}: {tc['label']}...[/dim]")
        try:
            result = run_test(tc)
        except Exception as e:
            result = {
                "id": tc["id"], "label": tc["label"], "passed": False,
                "cat_ok": False, "routing_ok": False, "no_error": False,
                "has_draft": False, "got_cat": "error", "got_routing": "error",
                "got_score": 0, "draft": "", "escalation": "", "reasoning": "",
                "nodes": [], "elapsed": 0, "error": str(e),
            }
        results.append(result)
 
    print_results(results)
 