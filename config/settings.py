"""
config/settings.py
──────────────────
Central configuration for the Jude Agent system.
All secrets come from environment variables — never hardcoded.
"""
 
import os
from dotenv import load_dotenv
 
load_dotenv()
 
# ── LLM ──────────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL       = "claude-sonnet-4-20250514"
MAX_TOKENS         = 2048
 
# ── Memory TTL (seconds) ──────────────────────────────────────────────────────
SHORT_TERM_TTL     = 60 * 60 * 4        # 4 hours
EPISODIC_MAX_ITEMS = 200                 # max episodes kept in memory
 
# ── Priority thresholds ───────────────────────────────────────────────────────
PRIORITY_AUTO_ESCALATE = 9              # score >= 9  → immediate alert to Jude
PRIORITY_AUTO_HANDLE   = 3             # score <= 3  → agent handles silently
# scores 4-8 → queue for Jude's approval
 
# ── Guardrails ────────────────────────────────────────────────────────────────
# Topics the agent must NEVER handle autonomously
SENSITIVE_TOPICS = [
    "legal", "court", "lawsuit", "eviction",
    "payment dispute", "contract termination",
    "police", "fraud", "emergency",
]
 
# Categories that always require Jude's explicit approval before responding
ALWAYS_REQUIRE_APPROVAL = [
    "legal",
    "financial_commitment",
    "new_client_onboarding",
    "complaint_escalated",
]
 
# ── Agent identity ─────────────────────────────────────────────────────────────
AGENT_NAME      = "J-OS"               # Jude's Operating System
OPERATOR_NAME   = "Jude"
OPERATOR_ROLE   = "Real Estate Operator, Lagos Nigeria"

# ── Twilio ────────────────────────────────────────────────────────────────────
TWILIO_ACCOUNT_SID      = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN       = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_NUMBER  = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")
TWILIO_PHONE_NUMBER     = os.getenv("TWILIO_PHONE_NUMBER", "")

# ── Jude personal details ─────────────────────────────────────────────────────
JUDE_PERSONAL_NUMBER    = os.getenv("JUDE_PERSONAL_NUMBER", "")

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN      = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID        = os.getenv("TELEGRAM_CHAT_ID", "")

# ── Deepgram ──────────────────────────────────────────────────────────────────
DEEPGRAM_API_KEY        = os.getenv("DEEPGRAM_API_KEY", "")
 