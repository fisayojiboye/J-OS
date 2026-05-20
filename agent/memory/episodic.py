"""
agent/memory/episodic.py
────────────────────────
EPISODIC MEMORY — the most overlooked layer.
 
Humans don't just store facts — they remember *experiences*.
This layer records what happened, when, the outcome, and significance.
 
Examples:
  "Client got angry because Jude delayed response for 2 days — deal nearly fell through."
  "The Lekki deal closed after Jude sent drone footage."
  "Mr Emeka responded well to WhatsApp voice notes, not text."
 
This is what lets the agent reason like: "Last time we handled X this way,
the outcome was Y — we should try Z instead."
 
Backend: JSON for MVP.
"""
 
import json
import time
import uuid
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field
from config.settings import EPISODIC_MAX_ITEMS
 
 
DATA_PATH = Path("data/episodic.json")
 
Significance = Literal["low", "medium", "high", "critical"]
Outcome      = Literal["positive", "negative", "neutral", "unknown"]
 
 
class Episode(BaseModel):
    id:           str  = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    title:        str                        # short label, e.g. "Emeka deal negotiation"
    what:         str                        # what happened
    when:         float = Field(default_factory=time.time)
    who:          str   = "unknown"          # client/contact involved
    outcome:      Outcome = "unknown"
    significance: Significance = "medium"
    lesson:       str   = ""                # what the agent should learn from this
    tags:         list[str] = Field(default_factory=list)
    context:      dict  = Field(default_factory=dict)
 
 
class EpisodicMemory:
    """
    Chronological log of significant events and their outcomes.
    Used by the agent to reason from past experience.
    """
 
    def __init__(self, path: Path = DATA_PATH, max_items: int = EPISODIC_MAX_ITEMS):
        self._path      = path
        self._max_items = max_items
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._episodes: list[Episode] = []
        self._load()
 
    # ── Persistence ───────────────────────────────────────────────────────────
 
    def _load(self) -> None:
        if self._path.exists():
            raw = json.loads(self._path.read_text())
            self._episodes = [Episode(**e) for e in raw]
 
    def _save(self) -> None:
        raw = [e.model_dump() for e in self._episodes]
        self._path.write_text(json.dumps(raw, indent=2, default=str))
 
    # ── Core operations ───────────────────────────────────────────────────────
 
    def record(
        self,
        title:        str,
        what:         str,
        who:          str          = "unknown",
        outcome:      Outcome      = "unknown",
        significance: Significance = "medium",
        lesson:       str          = "",
        tags:         list[str]    = None,
        context:      dict         = None,
    ) -> Episode:
        episode = Episode(
            title=title,
            what=what,
            who=who,
            outcome=outcome,
            significance=significance,
            lesson=lesson,
            tags=tags or [],
            context=context or {},
        )
        self._episodes.append(episode)
 
        # Trim to max — keep most significant first if over limit
        if len(self._episodes) > self._max_items:
            # Sort: critical > high > medium > low, then by recency
            order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            self._episodes.sort(
                key=lambda e: (order[e.significance], -e.when)
            )
            self._episodes = self._episodes[:self._max_items]
 
        self._save()
        return episode
 
    def get_by_person(self, who: str) -> list[Episode]:
        who_lower = who.lower()
        return [e for e in self._episodes if who_lower in e.who.lower()]
 
    def get_by_tag(self, tag: str) -> list[Episode]:
        return [e for e in self._episodes if tag in e.tags]
 
    def get_recent(self, n: int = 10) -> list[Episode]:
        return sorted(self._episodes, key=lambda e: e.when, reverse=True)[:n]
 
    def get_critical(self) -> list[Episode]:
        return [e for e in self._episodes if e.significance == "critical"]
 
    def search(self, keyword: str) -> list[Episode]:
        kw = keyword.lower()
        return [
            e for e in self._episodes
            if kw in e.what.lower() or kw in e.title.lower()
            or kw in e.lesson.lower() or kw in e.who.lower()
        ]
 
    # ── Snapshot for LLM ─────────────────────────────────────────────────────
 
    def to_prompt_block(self, person: str = None, limit: int = 5) -> str:
        if person:
            episodes = self.get_by_person(person)
        else:
            episodes = self.get_recent(limit)
 
        if not episodes:
            return ""
 
        lines = ["=== EPISODIC MEMORY (past experiences) ==="]
        for e in episodes[:limit]:
            ts = time.strftime("%Y-%m-%d", time.localtime(e.when))
            lines.append(f"\n[{ts}] {e.title} (with {e.who})")
            lines.append(f"  What happened: {e.what}")
            lines.append(f"  Outcome: {e.outcome} | Significance: {e.significance}")
            if e.lesson:
                lines.append(f"  Lesson: {e.lesson}")
 
        return "\n".join(lines)
 
    # ── Seed with known past events ───────────────────────────────────────────
 
    def seed_examples(self) -> None:
        """Pre-load known significant past events for context."""
        self.record(
            title="Client angry over delayed response",
            what="A client (Mr Chukwudi) waited 2 days for Jude to respond to a property inquiry. "
                 "He called twice and was close to going to a competitor.",
            who="Mr Chukwudi",
            outcome="negative",
            significance="high",
            lesson="Never let WhatsApp messages from serious buyers sit longer than 4 hours. "
                   "Always send an acknowledgment even if full response takes longer.",
            tags=["response_time", "client_management", "whatsapp"],
        )
        self.record(
            title="Drone footage closed Lekki deal",
            what="After stalled negotiations on a Lekki property, Jude sent a drone footage video "
                 "of the estate. Client immediately committed and paid deposit the next day.",
            who="Mrs Adaeze",
            outcome="positive",
            significance="high",
            lesson="Visual content (drone footage, virtual tours) dramatically accelerates "
                   "decisions for high-ticket properties. Use it early, not as a last resort.",
            tags=["closing_tactics", "video", "lekki", "high_value"],
        )
        self.record(
            title="Missed exam due to scheduling failure",
            what="Jude forgot about a professional exam. He left home to book a hotel the night "
                 "before, thinking it was the next day, but the exam had already happened.",
            who="Jude",
            outcome="negative",
            significance="critical",
            lesson="All exams and certification deadlines must be flagged 1 week, 3 days, 1 day, "
                   "and 3 hours before. No exceptions. These should also be cross-checked monthly.",
            tags=["scheduling", "exams", "critical_failure"],
        )
 