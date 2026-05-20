"""
agent/memory/long_term.py
─────────────────────────
LONG-TERM MEMORY — the real second brain.
 
Stores facts that persist indefinitely:
  • client relationships & preferences
  • Jude's routines & commitments
  • repeated behaviours
  • important personal/professional facts
 
Backend: JSON file for MVP (swap for PostgreSQL + pgvector in production).
Organised into named "namespaces" for clean retrieval.
"""
 
import json
import time
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field
 
 
DATA_PATH = Path("data/long_term.json")
 
 
class MemoryEntry(BaseModel):
    key:         str
    value:       Any
    namespace:   str   = "general"      # "clients" | "jude" | "business" | "general"
    created_at:  float = Field(default_factory=time.time)
    updated_at:  float = Field(default_factory=time.time)
    tags:        list[str] = Field(default_factory=list)
    source:      str   = "manual"       # "manual" | "agent_learned" | "user_confirmed"
 
 
class LongTermMemory:
    """
    Persistent key-value store organised by namespace.
 
    Namespaces:
      jude        — Jude's own preferences, routines, habits
      clients     — per-client facts and preferences
      business    — business rules, pricing, processes
      contacts    — important contacts and relationships
      general     — catch-all
    """
 
    def __init__(self, path: Path = DATA_PATH):
        self._path   = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._store: dict[str, dict[str, MemoryEntry]] = {}
        self._load()
 
    # ── Persistence ───────────────────────────────────────────────────────────
 
    def _load(self) -> None:
        if self._path.exists():
            raw = json.loads(self._path.read_text())
            for ns, entries in raw.items():
                self._store[ns] = {
                    k: MemoryEntry(**v) for k, v in entries.items()
                }
        else:
            self._store = {}
 
    def _save(self) -> None:
        raw = {
            ns: {k: e.model_dump() for k, e in entries.items()}
            for ns, entries in self._store.items()
        }
        self._path.write_text(json.dumps(raw, indent=2, default=str))
 
    # ── CRUD ──────────────────────────────────────────────────────────────────
 
    def set(
        self,
        key:       str,
        value:     Any,
        namespace: str       = "general",
        tags:      list[str] = None,
        source:    str       = "manual",
    ) -> None:
        ns = self._store.setdefault(namespace, {})
        if key in ns:
            existing         = ns[key]
            existing.value   = value
            existing.updated_at = time.time()
            existing.tags    = tags or existing.tags
        else:
            ns[key] = MemoryEntry(
                key=key, value=value, namespace=namespace,
                tags=tags or [], source=source,
            )
        self._save()
 
    def get(self, key: str, namespace: str = "general") -> Any | None:
        return self._store.get(namespace, {}).get(key, None)
 
    def get_value(self, key: str, namespace: str = "general") -> Any | None:
        entry = self.get(key, namespace)
        return entry.value if entry else None
 
    def delete(self, key: str, namespace: str = "general") -> bool:
        ns = self._store.get(namespace, {})
        if key in ns:
            del ns[key]
            self._save()
            return True
        return False
 
    def search_by_tag(self, tag: str) -> list[MemoryEntry]:
        results = []
        for ns_entries in self._store.values():
            for entry in ns_entries.values():
                if tag in entry.tags:
                    results.append(entry)
        return results
 
    def get_namespace(self, namespace: str) -> dict[str, Any]:
        """Return all key-value pairs in a namespace."""
        return {
            k: e.value for k, e in self._store.get(namespace, {}).items()
        }
 
    def list_all(self) -> dict[str, dict[str, Any]]:
        return {
            ns: {k: e.value for k, e in entries.items()}
            for ns, entries in self._store.items()
        }
 
    # ── Snapshot for LLM ─────────────────────────────────────────────────────
 
    def to_prompt_block(self, namespace: str = None) -> str:
        lines = ["=== LONG-TERM MEMORY ==="]
        namespaces = [namespace] if namespace else list(self._store.keys())
 
        for ns in namespaces:
            entries = self._store.get(ns, {})
            if not entries:
                continue
            lines.append(f"\n[{ns.upper()}]")
            for key, entry in entries.items():
                lines.append(f"  • {key}: {entry.value}")
 
        return "\n".join(lines) if len(lines) > 1 else ""
 
    # ── Seed with Jude's initial known facts ─────────────────────────────────
 
    def seed_jude_profile(self) -> None:
        """
        Pre-load known facts about Jude.
        In production, this comes from an onboarding questionnaire.
        """
        jude_facts = {
            "inspection_preference":   "Prefers property inspections after 12 PM",
            "meeting_weakness":        "Often forgets evening meetings — always send reminders",
            "response_style":          "Direct, brief, professional. Never overly formal.",
            "negotiation_style":       "Usually offers installment options when clients request price reductions",
            "working_hours":           "Active 9AM–8PM Lagos time (WAT)",
            "primary_markets":         "Lekki, Victoria Island, Ikoyi, Ajah",
            "business_name":           "Jude's real estate business",
            "preferred_comms":         "WhatsApp first, calls second, email for formal docs",
            "recurring_commitments":   "Tuesday team meetings",
            "language":                "English (Nigerian context, Lagos slang acceptable with known clients)",
        }
        for key, value in jude_facts.items():
            self.set(key, value, namespace="jude", source="seed")
 