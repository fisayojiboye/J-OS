"""
agent/memory/priority.py
────────────────────────
PRIORITY MEMORY — where intelligence shows.
 
Humans forget because everything feels equally important.
This layer scores and ranks:
  • urgency         (how soon does this need attention?)
  • importance      (what's the business/life impact?)
  • business value  (revenue potential?)
  • deadline risk   (is there a hard deadline?)
  • emotional weight (relationship risk if ignored?)
 
Priority Score: 1–10
  9–10  → AUTO-ESCALATE to Jude immediately
  6–8   → Queue for Jude approval (draft ready)
  4–5   → Handle with low autonomy, inform Jude in daily digest
  1–3   → Handle autonomously and silently
 
Also maintains a queue of pending items ranked by priority.
"""
 
import json
import time
import uuid
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field
from config.settings import PRIORITY_AUTO_ESCALATE, PRIORITY_AUTO_HANDLE
 
 
DATA_PATH = Path("data/priority_queue.json")
 
RoutingDecision = Literal["auto_escalate", "queue_approval", "inform_only", "handle_silently"]
 
 
class PriorityItem(BaseModel):
    id:              str  = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    title:           str
    body:            str
    source:          str   = "unknown"    # "whatsapp" | "email" | "call" | "calendar"
    sender:          str   = "unknown"
    score:           int   = 5            # 1–10
    urgency:         int   = 5            # 1–10
    importance:      int   = 5            # 1–10
    business_value:  int   = 5           # 1–10
    deadline_risk:   int   = 5            # 1–10
    routing:         RoutingDecision = "queue_approval"
    created_at:      float = Field(default_factory=time.time)
    resolved:        bool  = False
    resolution_note: str   = ""
    tags:            list[str] = Field(default_factory=list)
 
 
# ── Scoring rules — the agent's priority intelligence ─────────────────────────
 
KEYWORD_BOOSTS: dict[str, int] = {
    # Urgency boosters
    "emergency":         5,
    "urgent":            4,
    "asap":              4,
    "immediately":       4,
    "today":             3,
    "tonight":           3,
    "now":               4,
    # Business value boosters
    "payment":           4,
    "deposit":           4,
    "transfer":          4,
    "ready to buy":      5,
    "interested":        2,
    "how much":          2,
    # Risk boosters
    "legal":             5,
    "court":             5,
    "eviction":          5,
    "lawsuit":           5,
    "complaint":         3,
    "threatening":       4,
    "police":            5,
    # Deadline risk
    "exam":              5,
    "deadline":          4,
    "expires":           4,
    "last chance":       4,
    "close of business": 3,
    "tomorrow":          2,
    # Dampeners
    "just checking":    -2,
    "whenever":         -2,
    "no rush":          -3,
    "quick question":   -1,
}
 
 
class PriorityMemory:
    """
    Scores incoming items and maintains a ranked queue.
    This is the traffic controller that decides what Jude sees and when.
    """
 
    def __init__(self, path: Path = DATA_PATH):
        self._path  = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._queue: list[PriorityItem] = []
        self._load()
 
    # ── Persistence ───────────────────────────────────────────────────────────
 
    def _load(self) -> None:
        if self._path.exists():
            raw = json.loads(self._path.read_text())
            self._queue = [PriorityItem(**item) for item in raw]
 
    def _save(self) -> None:
        raw = [item.model_dump() for item in self._queue]
        self._path.write_text(json.dumps(raw, indent=2, default=str))
 
    # ── Scoring engine ────────────────────────────────────────────────────────
 
    def score_message(
        self,
        text:     str,
        source:   str = "unknown",
        sender:   str = "unknown",
        metadata: dict = None,
    ) -> dict:
        """
        Heuristic scorer. In production, this is augmented by an LLM call.
        Returns a score dict with breakdown and routing decision.
        """
        metadata   = metadata or {}
        text_lower = text.lower()
 
        # Base scores by source
        source_base = {"call": 6, "whatsapp": 5, "email": 4, "calendar": 7}.get(source, 5)
 
        # Keyword analysis
        boost = 0
        triggered_keywords = []
        for keyword, weight in KEYWORD_BOOSTS.items():
            if keyword in text_lower:
                boost += weight
                triggered_keywords.append(keyword)
 
        # Known VIP sender boost (would be a DB lookup in production)
        vip_boost = 2 if metadata.get("is_vip", False) else 0
 
        # Compute sub-scores
        urgency        = min(10, max(1, source_base + (boost // 2) + vip_boost))
        importance     = min(10, max(1, source_base + vip_boost + (1 if "payment" in text_lower else 0)))
        business_value = min(10, max(1, 5 + vip_boost + (3 if any(k in text_lower for k in ["payment", "buy", "deposit"]) else 0)))
        deadline_risk  = min(10, max(1, 5 + (3 if any(k in text_lower for k in ["exam", "deadline", "expires", "tonight", "tomorrow"]) else 0)))
 
        # Final composite score (weighted average)
        score = round(
            (urgency * 0.35)
            + (importance * 0.25)
            + (business_value * 0.25)
            + (deadline_risk * 0.15)
        )
 
        # Routing decision
        if score >= PRIORITY_AUTO_ESCALATE:
            routing: RoutingDecision = "auto_escalate"
        elif score >= 6:
            routing = "queue_approval"
        elif score >= 4:
            routing = "inform_only"
        else:
            routing = "handle_silently"
 
        return {
            "score":          score,
            "urgency":        urgency,
            "importance":     importance,
            "business_value": business_value,
            "deadline_risk":  deadline_risk,
            "routing":        routing,
            "keywords_hit":   triggered_keywords,
        }
 
    # ── Queue management ──────────────────────────────────────────────────────
 
    def enqueue(
        self,
        title:    str,
        body:     str,
        source:   str = "unknown",
        sender:   str = "unknown",
        metadata: dict = None,
        tags:     list[str] = None,
    ) -> PriorityItem:
        score_data = self.score_message(body, source, sender, metadata)
        item = PriorityItem(
            title=title,
            body=body,
            source=source,
            sender=sender,
            score=score_data["score"],
            urgency=score_data["urgency"],
            importance=score_data["importance"],
            business_value=score_data["business_value"],
            deadline_risk=score_data["deadline_risk"],
            routing=score_data["routing"],
            tags=tags or [],
        )
        self._queue.append(item)
        self._save()
        return item
 
    def get_pending(self) -> list[PriorityItem]:
        """Return unresolved items sorted by score descending."""
        pending = [i for i in self._queue if not i.resolved]
        return sorted(pending, key=lambda i: i.score, reverse=True)
 
    def resolve(self, item_id: str, note: str = "") -> bool:
        for item in self._queue:
            if item.id == item_id:
                item.resolved = True
                item.resolution_note = note
                self._save()
                return True
        return False
 
    def get_escalations(self) -> list[PriorityItem]:
        return [i for i in self._queue if i.routing == "auto_escalate" and not i.resolved]
 
    # ── Snapshot for LLM ─────────────────────────────────────────────────────
 
    def to_prompt_block(self) -> str:
        pending = self.get_pending()[:5]
        if not pending:
            return ""
 
        lines = ["=== PRIORITY QUEUE (top pending items) ==="]
        for item in pending:
            lines.append(f"\n[Score: {item.score}/10 | {item.routing.upper()}]")
            lines.append(f"  From: {item.sender} via {item.source}")
            lines.append(f"  Subject: {item.title}")
            lines.append(f"  Preview: {item.body[:100]}...")
 
        return "\n".join(lines)
 