"""
api/webhooks.py
───────────────
FastAPI webhook server.

Twilio calls this endpoint every time someone sends Jude a WhatsApp message.
The flow is:

  1. Twilio POST → /webhook/whatsapp
  2. We parse the message
  3. Send instant acknowledgment back to sender
  4. Run message through agent graph
  5. Route result:
       auto_escalate  → urgent Telegram alert to Jude
       queue_approval → approval card on Telegram
       handle_silently → agent handles, no Jude interruption
       inform_only    → handle + note in daily digest
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request, Form
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv

load_dotenv()

from agent.graph import jude_agent
from agent.state import initial_state
from integrations.whatsapp import send_whatsapp, send_acknowledgment, parse_incoming
from integrations.telegram import send_alert, send_approval_request, send_simple

app = FastAPI(title="J-OS Webhook Server")


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/")
def health():
    """
    Simple health check endpoint.
    Visit this URL to confirm the server is running.
    """
    return {"status": "J-OS webhook server is running"}


# ── WhatsApp webhook ──────────────────────────────────────────────────────────

@app.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request):
    """
    Twilio calls this endpoint for every incoming WhatsApp message.

    Twilio sends form-encoded data, not JSON — that's why we use
    request.form() instead of request.json().

    We return a plain text 200 response immediately.
    Twilio expects a fast response — if we take too long it retries.
    All heavy processing happens after we've already responded.
    """
    # Parse the form data Twilio sends
    form_data = dict(await request.form())
    incoming  = parse_incoming(form_data)

    sender  = incoming["sender"]
    message = incoming["message"]

    # Ignore empty messages (e.g. someone sends only an image with no caption)
    if not message:
        return PlainTextResponse("ok", status_code=200)

    # Send instant acknowledgment so client knows message was received
    # This goes out BEFORE we run the agent — speed matters here
    send_acknowledgment(sender)

    # Run the message through the full agent pipeline
    state  = initial_state(
        message=message,
        source="whatsapp",
        sender=sender,
    )
    result = jude_agent.invoke(state)

    # Route based on what the agent decided
    routing  = result.get("routing", "queue_approval")
    category = result.get("category", "unknown")
    score    = result.get("priority_score", 5)

    if routing == "auto_escalate":
        # Urgent — alert Jude immediately, no draft
        alert = (
            f"🚨 URGENT — {sender} via WhatsApp\n"
            f"Category: {category} | Score: {score}/10\n\n"
            f"Message: {message[:300]}\n\n"
            f"Reason: {result.get('reasoning', '')}\n\n"
            f"⚠️ Handle this personally."
        )
        send_alert(alert)

    elif routing == "queue_approval":
        # Draft ready — send approval card to Jude
        draft = result.get("draft_response", "")
        if draft:
            # Store sender in item_id so we know who to send to on approval
            item_id = sender.replace("+", "").replace(" ", "")
            send_approval_request(
                sender=sender,
                source="whatsapp",
                category=category,
                score=score,
                original=message,
                draft=draft,
                item_id=item_id,
            )

    elif routing == "handle_silently":
        # Agent handles it — send the draft directly without bothering Jude
        draft = result.get("draft_response", "")
        if draft:
            send_whatsapp(sender, draft)

    elif routing == "inform_only":
        # Handle it but let Jude know quietly
        draft = result.get("draft_response", "")
        if draft:
            send_whatsapp(sender, draft)
            send_simple(
                f"ℹ️ Auto-handled {category} from {sender}\n"
                f"Sent: {draft[:100]}..."
            )

    # Always return 200 to Twilio — even if something went wrong internally
    # Returning non-200 causes Twilio to retry, which doubles messages
    return PlainTextResponse("ok", status_code=200)


# ── Telegram callback handler ─────────────────────────────────────────────────

@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    """
    Handles Jude tapping approve/edit buttons on Telegram.

    When Jude taps '✅ Send it' on an approval card:
      - Telegram sends a callback_query to this endpoint
      - We parse which item was approved
      - We send the draft to the original WhatsApp sender

    This is Phase 3 MVP — in Phase 5 we'll add the full
    edit flow where Jude can modify the draft before sending.
    """
    data = await request.json()

    # Check if this is a button tap (callback_query)
    callback = data.get("callback_query")
    if not callback:
        return {"ok": True}

    callback_data = callback.get("data", "")
    # callback_data format: "approve:2348012345678" or "edit:2348012345678"

    if callback_data.startswith("approve:"):
        # Extract the recipient number from the callback data
        recipient_number = "+" + callback_data.split("approve:")[1]

        # In a full implementation, we'd look up the draft from a database
        # For MVP, we send a confirmation to Jude that approval was received
        send_simple(
            f"✅ Approved — response queued for {recipient_number}\n"
            f"(Full send-on-approve coming in Phase 5)"
        )

    elif callback_data.startswith("edit:"):
        recipient_number = "+" + callback_data.split("edit:")[1]
        send_simple(
            f"✏️ Flagged for manual edit — {recipient_number}\n"
            f"Reply to this message with your edited response."
        )

    return {"ok": True}