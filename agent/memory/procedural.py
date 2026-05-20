"""
agent/memory/procedural.py
──────────────────────────
PROCEDURAL MEMORY — "how things are done around here."
 
This is Jude's business playbook embedded in the agent.
It stores:
  • how Jude qualifies leads
  • how he handles inspections
  • his negotiation style
  • follow-up sequences
  • standard operating procedures
 
Eventually the agent learns from patterns:
  "When client asks for price reduction → Jude usually offers installment options."
 
Backend: JSON for MVP (could evolve to a vector store for fuzzy matching).
"""
 
import json
import time
from pathlib import Path
from pydantic import BaseModel, Field
 
 
DATA_PATH = Path("data/procedural.json")
 
 
class Procedure(BaseModel):
    name:        str
    trigger:     str          # "when X happens..."
    steps:       list[str]    # ordered steps
    category:    str = "general"   # "lead", "inspection", "negotiation", "followup", "comms"
    notes:       str = ""
    created_at:  float = Field(default_factory=time.time)
    updated_at:  float = Field(default_factory=time.time)
 
 
class ProceduralMemory:
    """
    Stores how Jude operates — his standard playbooks and procedures.
    The agent uses these to act in his style, not just in his words.
    """
 
    def __init__(self, path: Path = DATA_PATH):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._procedures: dict[str, Procedure] = {}
        self._load()
 
    # ── Persistence ───────────────────────────────────────────────────────────
 
    def _load(self) -> None:
        if self._path.exists():
            raw = json.loads(self._path.read_text())
            self._procedures = {k: Procedure(**v) for k, v in raw.items()}
 
    def _save(self) -> None:
        raw = {k: p.model_dump() for k, p in self._procedures.items()}
        self._path.write_text(json.dumps(raw, indent=2, default=str))
 
    # ── Core operations ───────────────────────────────────────────────────────
 
    def add(
        self,
        name:     str,
        trigger:  str,
        steps:    list[str],
        category: str = "general",
        notes:    str = "",
    ) -> Procedure:
        proc = Procedure(
            name=name, trigger=trigger,
            steps=steps, category=category, notes=notes,
        )
        self._procedures[name] = proc
        self._save()
        return proc
 
    def get(self, name: str) -> Procedure | None:
        return self._procedures.get(name)
 
    def get_by_category(self, category: str) -> list[Procedure]:
        return [p for p in self._procedures.values() if p.category == category]
 
    def update_steps(self, name: str, steps: list[str]) -> bool:
        if name not in self._procedures:
            return False
        self._procedures[name].steps = steps
        self._procedures[name].updated_at = time.time()
        self._save()
        return True
 
    def find_relevant(self, situation: str) -> list[Procedure]:
        """Simple keyword match to find relevant procedures for a situation."""
        sit_lower = situation.lower()
        matches = []
        for proc in self._procedures.values():
            if (
                any(word in sit_lower for word in proc.trigger.lower().split())
                or any(word in sit_lower for word in proc.name.lower().split())
            ):
                matches.append(proc)
        return matches
 
    # ── Snapshot for LLM ─────────────────────────────────────────────────────
 
    def to_prompt_block(self, category: str = None) -> str:
        procs = (
            self.get_by_category(category)
            if category
            else list(self._procedures.values())
        )
        if not procs:
            return ""
 
        lines = ["=== PROCEDURAL MEMORY (how Jude operates) ==="]
        for p in procs:
            lines.append(f"\n[{p.name}]")
            lines.append(f"  Trigger: {p.trigger}")
            for i, step in enumerate(p.steps, 1):
                lines.append(f"  Step {i}: {step}")
            if p.notes:
                lines.append(f"  Notes: {p.notes}")
 
        return "\n".join(lines)
 
    # ── Seed Jude's known playbooks ───────────────────────────────────────────
 
    def seed_playbooks(self) -> None:
        """Load Jude's known operating procedures."""
 
        self.add(
            name="lead_qualification",
            trigger="When a new inquiry comes in about a property",
            steps=[
                "Greet warmly, confirm their name and how they heard about the property.",
                "Ask: What type of property are you looking for? (buy/rent, size, location)",
                "Ask: What is your budget range?",
                "Ask: What is your timeline? (urgent, 1–3 months, flexible)",
                "Ask: Is this for personal use or investment?",
                "If serious (budget confirmed + timeline clear): schedule inspection.",
                "If vague: send property catalogue link and follow up in 48 hours.",
            ],
            category="lead",
            notes="Never skip the budget question. Time-wasters become obvious at step 3.",
        )
 
        self.add(
            name="inspection_scheduling",
            trigger="When a qualified lead wants to see a property",
            steps=[
                "Confirm property address and availability with Jude's calendar.",
                "Offer time slots after 12 PM on weekdays.",
                "Confirm client's transport — offer directions or meeting point if needed.",
                "Send property fact sheet to client 2 hours before inspection.",
                "Remind Jude 1 hour before via Telegram.",
                "After inspection: follow up within 6 hours to get their feedback.",
            ],
            category="inspection",
            notes="Jude prefers afternoon inspections. Never book before 12 PM.",
        )
 
        self.add(
            name="price_negotiation",
            trigger="When a client requests a price reduction or says it's too expensive",
            steps=[
                "Acknowledge their concern empathetically — don't dismiss.",
                "Restate the value: location, finishing, developer reputation.",
                "If still resistant: offer installment payment plan as alternative.",
                "If they want more than 10% off: escalate to Jude — do not commit.",
                "Document the offer discussed and client's response.",
            ],
            category="negotiation",
            notes="Jude's bottom line: never go beyond 10% discount without his approval. "
                  "Installment options are the primary tool — use them early.",
        )
 
        self.add(
            name="client_followup_sequence",
            trigger="After an inspection or proposal has been sent",
            steps=[
                "Day 0 (same day): Send thank-you message + inspection summary.",
                "Day 2: Check in — any questions or concerns?",
                "Day 5: Share a relevant property comparison or market update.",
                "Day 10: Soft close — ask if they're ready to proceed.",
                "Day 14: Final follow-up. If no response, move to dormant list.",
            ],
            category="followup",
            notes="Do not exceed one message per 2 days. Clients disengage if over-messaged.",
        )
 
        self.add(
            name="payment_confirmation",
            trigger="When a client indicates they want to pay or close a deal",
            steps=[
                "Immediately escalate to Jude — do not proceed autonomously.",
                "Confirm: full payment or installment?",
                "Send official payment details (bank account / reference) only after Jude confirms.",
                "Log payment date and amount in client record.",
                "Send receipt acknowledgment within 1 hour of confirmed payment.",
                "Schedule document signing within 48 hours.",
            ],
            category="lead",
            notes="NEVER share payment details without Jude's explicit go-ahead. Always escalate.",
        )
 