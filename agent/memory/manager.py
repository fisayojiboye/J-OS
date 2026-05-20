"""
agent/memory/manager.py
───────────────────────
MEMORY MANAGER — the unified interface.
 
This is the single object the LangGraph nodes talk to.
It orchestrates reads and writes across all 5 memory layers
and assembles the memory context block that gets injected
into every LLM prompt.
"""
 
from .short_term  import ShortTermMemory
from .long_term   import LongTermMemory
from .episodic    import EpisodicMemory
from .procedural  import ProceduralMemory
from .priority    import PriorityMemory
 
 
class MemoryManager:
    """
    Unified facade over all 5 memory layers.
    The graph nodes use this — they never touch the individual stores directly.
    """
 
    def __init__(self, seed: bool = True):
        self.short_term  = ShortTermMemory()
        self.long_term   = LongTermMemory()
        self.episodic    = EpisodicMemory()
        self.procedural  = ProceduralMemory()
        self.priority    = PriorityMemory()
 
        if seed:
            self._seed_if_empty()
 
    def _seed_if_empty(self) -> None:
        """Seed initial knowledge if stores are empty (first run)."""
        if not self.long_term.get_namespace("jude"):
            self.long_term.seed_jude_profile()
 
        if not self.episodic.get_recent(1):
            self.episodic.seed_examples()
 
        if not self.procedural._procedures:
            self.procedural.seed_playbooks()
 
    # ── Context assembly for LLM ──────────────────────────────────────────────
 
    def build_context_block(
        self,
        person:            str  = None,
        include_procedure: bool = True,
        include_priority:  bool = True,
    ) -> str:
        """
        Assemble all memory layers into a single context string
        for injection into the LLM system prompt.
 
        Layers included (in order):
          1. Short-term  (current state)
          2. Long-term   (persistent facts)
          3. Episodic    (past experiences — filtered by person if given)
          4. Procedural  (how to handle the situation)
          5. Priority    (what's pending and urgent)
        """
        blocks = []
 
        st = self.short_term.to_prompt_block()
        if st:
            blocks.append(st)
 
        lt = self.long_term.to_prompt_block(namespace="jude")
        if lt:
            blocks.append(lt)
 
        ep = self.episodic.to_prompt_block(person=person, limit=3)
        if ep:
            blocks.append(ep)
 
        if include_procedure:
            proc = self.procedural.to_prompt_block()
            if proc:
                blocks.append(proc)
 
        if include_priority:
            pq = self.priority.to_prompt_block()
            if pq:
                blocks.append(pq)
 
        return "\n\n".join(blocks)
 
    # ── Convenience write methods ─────────────────────────────────────────────
 
    def remember_fact(self, key: str, value: str, namespace: str = "general") -> None:
        """Store a long-term fact learned during a conversation."""
        self.long_term.set(key, value, namespace=namespace, source="agent_learned")
 
    def remember_episode(
        self,
        title:  str,
        what:   str,
        who:    str   = "unknown",
        outcome: str  = "unknown",
        lesson: str   = "",
        tags:   list  = None,
    ) -> None:
        self.episodic.record(
            title=title, what=what, who=who,
            outcome=outcome, lesson=lesson, tags=tags or [],
        )
 
    def get_client_context(self, client_name: str) -> str:
        """Pull everything we know about a specific client."""
        lines = [f"=== CONTEXT FOR: {client_name} ==="]
 
        # Long-term facts
        client_key = client_name.lower().replace(" ", "_")
        client_data = self.long_term.get_value(client_key, namespace="clients")
        if client_data:
            lines.append(f"Known facts: {client_data}")
 
        # Past episodes
        episodes = self.episodic.get_by_person(client_name)
        if episodes:
            lines.append("Past experiences:")
            for ep in episodes[-3:]:
                lines.append(f"  • {ep.title} → outcome: {ep.outcome}")
                if ep.lesson:
                    lines.append(f"    Lesson: {ep.lesson}")
 
        return "\n".join(lines) if len(lines) > 1 else f"No prior context for {client_name}."
 