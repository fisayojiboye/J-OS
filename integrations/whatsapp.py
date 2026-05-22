import os
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from dotenv import load_dotenv

load_dotenv()

ACCOUNT_SID      = os.getenv("TWILIO_ACCOUNT_SID", "")
AUTH_TOKEN       = os.getenv("TWILIO_AUTH_TOKEN", "")
FROM_NUMBER      = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")


def _get_client() -> Client:
    """Create Twilio client. Called fresh each time — no stale connections."""
    return Client(ACCOUNT_SID, AUTH_TOKEN)


def send_whatsapp(to: str, body: str) -> dict:
    """
    Send a WhatsApp message via Twilio.

    Args:
        to:   Recipient number in format '+2348012345678'
              We add 'whatsapp:' prefix automatically.
        body: Message text to send.

    Returns:
        {"success": True, "sid": "..."} or {"success": False, "error": "..."}
    """
    # Normalize the number — add whatsapp: prefix if not present
    if not to.startswith("whatsapp:"):
        to = f"whatsapp:{to}"

    try:
        client  = _get_client()
        message = client.messages.create(
            from_=FROM_NUMBER,
            to=to,
            body=body,
        )
        return {"success": True, "sid": message.sid}

    except TwilioRestException as e:
        print(f"[WhatsApp] Send failed to {to}: {e}")
        return {"success": False, "error": str(e)}


def send_acknowledgment(to: str) -> dict:
    """
    Send an instant acknowledgment when a message arrives.
    Goes out immediately — before the agent even finishes processing.
    This stops clients thinking Jude is ignoring them.
    """
    body = (
        "Hi, thanks for your message. "
        "Jude will get back to you shortly."
    )
    return send_whatsapp(to, body)


def parse_incoming(form_data: dict) -> dict:
    """
    Parse Twilio's incoming webhook payload into a clean dict.

    Twilio sends form data (not JSON) when a WhatsApp message arrives.
    This converts it into the format our agent expects.

    Args:
        form_data: The raw form dict from the webhook POST request.

    Returns:
        {
          "sender":  "+2348012345678",
          "message": "Hello, I saw your listing...",
          "source":  "whatsapp",
          "media":   []   # list of media URLs if they sent images
        }
    """
    # Extract sender — Twilio sends "whatsapp:+234..." so we strip the prefix
    raw_from = form_data.get("From", "")
    sender   = raw_from.replace("whatsapp:", "").strip()

    # The message body
    message  = form_data.get("Body", "").strip()

    # Any media attachments (images, documents)
    num_media = int(form_data.get("NumMedia", 0))
    media     = [
        form_data.get(f"MediaUrl{i}", "")
        for i in range(num_media)
    ]

    return {
        "sender":  sender,
        "message": message,
        "source":  "whatsapp",
        "media":   media,
    }