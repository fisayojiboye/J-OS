"""
integrations/voice.py
─────────────────────
Handles all voice call logic for the Jude Agent.

What happens when someone calls +1(912)922-3120:

  1. Twilio receives the call and hits /webhook/voice/inbound
  2. We play a brief screening message
  3. We ask the caller to state their name and reason for calling
  4. We record their response (caller screening recording)
  5. We forward the call to Jude's personal number
  6. The ENTIRE call is recorded from start to finish
  7. When call ends, Twilio hits /webhook/voice/recording
  8. We transcribe and process the recording
  9. Jude gets a summary on Telegram

TwiML (Twilio Markup Language) is what we return to Twilio
to tell it what to do. It's XML that Twilio reads and executes.
"""

import os
from twilio.twiml.voice_response import VoiceResponse, Gather, Record, Dial
from twilio.rest import Client
from dotenv import load_dotenv

load_dotenv()

ACCOUNT_SID          = os.getenv("TWILIO_ACCOUNT_SID", "")
AUTH_TOKEN           = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER  = os.getenv("TWILIO_PHONE_NUMBER", "")
JUDE_PERSONAL_NUMBER = os.getenv("JUDE_PERSONAL_NUMBER", "")

# Base URL of our webhook server
# During development this is your ngrok URL
# In production it's your server domain
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "http://localhost:8000")


def get_client() -> Client:
    """Create fresh Twilio client."""
    return Client(ACCOUNT_SID, AUTH_TOKEN)


def handle_inbound_call(caller: str) -> str:
    """
    Called when someone dials +1(912)922-3120.

    Returns TwiML XML that tells Twilio exactly what to do:
      1. Play consent notice (legal requirement)
      2. Ask caller to state name + reason
      3. Record their response
      4. Forward to Jude's real number
      5. Record the full call

    Args:
        caller: The caller's phone number from Twilio

    Returns:
        TwiML XML string
    """
    response = VoiceResponse()

    # Step 1 — Consent notice
    # Legal requirement under NDPA — informs caller of recording
    # 'alice' is Twilio's built-in text-to-speech voice
    response.say(
        "Hello. You have reached Jude's property consultancy. "
        "This call may be recorded for quality and service purposes. "
        "Please hold while we connect you.",
        voice="alice",
        language="en-GB",    # British English sounds more professional
    )

    # Step 2 — Screen the caller
    # Ask them to state their name and reason before connecting
    # This gives us a searchable record even if Jude misses the call
    gather = Gather(
        action=f"{WEBHOOK_BASE_URL}/webhook/voice/screened",
        method="POST",
        timeout=8,           # Wait 8 seconds for them to speak
        finish_on_key="#",   # They can press # when done
    )
    gather.say(
        "Please state your name and briefly describe the reason for your call, "
        "then press hash or wait.",
        voice="alice",
        language="en-GB",
    )
    response.append(gather)

    # Fallback if they say nothing — connect directly
    response.say(
        "Connecting you now.",
        voice="alice",
    )
    response.redirect(f"{WEBHOOK_BASE_URL}/webhook/voice/connect")

    return str(response)


def connect_and_record(caller: str, screen_recording_url: str = None) -> str:
    """
    After screening, connect the caller to Jude and record the full call.

    The Dial verb connects caller to Jude's personal number.
    record=True on the Dial records the entire conversation.

    Args:
        caller:                The original caller's number
        screen_recording_url:  URL of the screening recording if captured

    Returns:
        TwiML XML string
    """
    response = VoiceResponse()

    response.say(
        "Connecting you to Jude now. Please hold.",
        voice="alice",
        language="en-GB",
    )

    # Dial Jude's personal number and record everything
    dial = Dial(
        record="record-from-answer",     # Start recording when Jude picks up
        recording_status_callback=f"{WEBHOOK_BASE_URL}/webhook/voice/recording",
        recording_status_callback_method="POST",
        timeout=30,                       # Ring for 30 seconds before giving up
        action=f"{WEBHOOK_BASE_URL}/webhook/voice/completed",
    )
    dial.number(
        JUDE_PERSONAL_NUMBER,
        status_callback=f"{WEBHOOK_BASE_URL}/webhook/voice/status",
        status_callback_method="POST",
    )
    response.append(dial)

    return str(response)


def handle_missed_call(caller: str) -> str:
    """
    Called when Jude doesn't answer.
    Takes a voicemail and notifies Jude on Telegram.

    Returns:
        TwiML XML string
    """
    response = VoiceResponse()

    response.say(
        "Jude is currently unavailable. "
        "Please leave a message after the tone and he will get back to you shortly. "
        "You can also reach him via WhatsApp on this number.",
        voice="alice",
        language="en-GB",
    )

    # Record voicemail — max 2 minutes
    response.record(
        max_length=120,
        action=f"{WEBHOOK_BASE_URL}/webhook/voice/voicemail",
        recording_status_callback=f"{WEBHOOK_BASE_URL}/webhook/voice/recording",
        recording_status_callback_method="POST",
        transcribe=False,    # We use Deepgram, not Twilio's transcription
        play_beep=True,
    )

    response.say(
        "Thank you for your message. Goodbye.",
        voice="alice",
    )

    return str(response)


def get_recording_url(recording_sid: str) -> str:
    """
    Fetch the MP3 download URL for a completed recording.

    Twilio stores recordings on their servers.
    We download and send to Deepgram for transcription.

    Args:
        recording_sid: The recording identifier from Twilio

    Returns:
        Direct MP3 download URL
    """
    return (
        f"https://api.twilio.com/2010-04-01/Accounts/"
        f"{ACCOUNT_SID}/Recordings/{recording_sid}.mp3"
    )


def get_call_details(call_sid: str) -> dict:
    """
    Fetch metadata about a completed call from Twilio.

    Returns duration, start time, caller, direction etc.
    Used to enrich the call summary sent to Jude.
    """
    try:
        client = get_client()
        call   = client.calls(call_sid).fetch()
        return {
            "sid":       call.sid,
            "from":      call.from_formatted,
            "to":        call.to_formatted,
            "duration":  call.duration,       # seconds
            "status":    call.status,
            "direction": call.direction,       # inbound / outbound
            "start":     str(call.start_time),
        }
    except Exception as e:
        return {"error": str(e)}