"""
agent/memory/short_term.py
──────────────────────────
SHORT-TERM MEMORY  — the agent's "working memory."
 
Stores:
  • current conversation thread
  • current active task
  • recent actions taken
  • temporary context (e.g. "Jude is negotiating Lekki deal right now")
 
Lifetime: minutes to hours (configurable TTL).
Backend:  in-process dict for MVP (swap for Redis in production).
"""
 
import time
from typing import Any
from pydantic import BaseModel, Field
from config.settings import SHORT_TERM_TTL
 
 
class ConversationTurn(BaseModel):
    role:      str          # "user" | "assistant" | "system"
    content:   str
    timestamp: float = Field(default_factory=time.time)
    source:    str = "unknown"   # "whatsapp" | "email" | "telegram" etc.
 
 
class ActiveTask(BaseModel):
    task_id:     str
    description: str
    started_at:  float = Field(default_factory=time.time)
    context:     dict  = Field(default_factory=dict)
 
 
class ShortTermMemory:
    """
    In-process working memory. Fast. Volatile.
    Automatically expires entries older than TTL.
    """
 
    def __init__(self, ttl_seconds: int = SHORT_TERM_TTL):
        self._ttl          = ttl_seconds
        self._conversation : list[ConversationTurn] = []
        self._active_task  : ActiveTask | None       = None
        self._recent_actions: list[dict]             = []
        self._temp_context : dict[str, Any]          = {}
        self._context_timestamps: dict[str, float]  = {}
 
    # ── Conversation ──────────────────────────────────────────────────────────
 
    def add_turn(self, role: str, content: str, source: str = "unknown") -> None:
        self._conversation.append(
            ConversationTurn(role=role, content=content, source=source)
        )
        # Keep last 20 turns only — prevents context bloat
        if len(self._conversation) > 20:
            self._conversation = self._conversation[-20:]
 
    def get_conversation(self) -> list[dict]:
        """Return conversation as list of {role, content} dicts for LLM."""
        return [{"role": t.role, "content": t.content} for t in self._conversation]
 
    def clear_conversation(self) -> None:
        self._conversation = []
 
    # ── Active task ───────────────────────────────────────────────────────────
 
    def set_task(self, task_id: str, description: str, context: dict = None) -> None:
        self._active_task = ActiveTask(
            task_id=task_id,
            description=description,
            context=context or {},
        )
 
    def get_task(self) -> ActiveTask | None:
        return self._active_task
 
    def clear_task(self) -> None:
        self._active_task = None
 
    # ── Recent actions ────────────────────────────────────────────────────────
 
    def log_action(self, action: str, result: str, metadata: dict = None) -> None:
        self._recent_actions.append({
            "action":    action,
            "result":    result,
            "metadata":  metadata or {},
            "timestamp": time.time(),
        })
        # Keep last 10 actions
        if len(self._recent_actions) > 10:
            self._recent_actions = self._recent_actions[-10:]
 
    def get_recent_actions(self) -> list[dict]:
        return self._recent_actions.copy()
 
    # ── Temporary context ─────────────────────────────────────────────────────
 
    def set_context(self, key: str, value: Any) -> None:
        self._temp_context[key]          = value
        self._context_timestamps[key]    = time.time()
 
    def get_context(self, key: str) -> Any | None:
        if key not in self._temp_context:
            return None
        # Expire stale entries
        if time.time() - self._context_timestamps[key] > self._ttl:
            del self._temp_context[key]
            del self._context_timestamps[key]
            return None
        return self._temp_context[key]
 
    def get_all_context(self) -> dict:
        """Return all non-expired context items."""
        now = time.time()
        valid = {
            k: v for k, v in self._temp_context.items()
            if now - self._context_timestamps.get(k, 0) <= self._ttl
        }
        return valid
 
    # ── Snapshot for LLM ─────────────────────────────────────────────────────
 
    def to_prompt_block(self) -> str:
        """Format current short-term state as a readable block for the LLM."""
        lines = ["=== SHORT-TERM MEMORY ==="]
 
        task = self.get_task()
        if task:
            lines.append(f"Active Task: {task.description}")
 
        ctx = self.get_all_context()
        if ctx:
            lines.append("Current Context:")
            for k, v in ctx.items():
                lines.append(f"  • {k}: {v}")
 
        actions = self.get_recent_actions()
        if actions:
            lines.append("Recent Actions:")
            for a in actions[-3:]:
                lines.append(f"  • {a['action']} → {a['result']}")
 
        return "\n".join(lines)
 