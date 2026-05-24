"""
integrations/transcription.py
──────────────────────────────
Transcription pipeline using Deepgram.

Flow:
  Recording URL (from Twilio)
       ↓
  Download audio
       ↓
  Send to Deepgram
       ↓
  Get transcript text
       ↓
  Send transcript to Claude
       ↓
  Extract structured insights:
    - caller name
    - key topics discussed
    - promises made
    - action items
    - client sentiment
    - follow-up needed?
       ↓
  Return everything for memory update
"""

import os
import json
import re
import httpx
import anthropic
from deepgram import DeepgramClient, PrerecordedOptions, FileSource
from dotenv import load_dotenv

load_dotenv()

DEEPGRAM_API_KEY  = os.getenv("DEEPGRAM_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN  = os.getenv("TWILIO_AUTH_TOKEN", "")


def transcribe_recording(recording_url: str) -> dict:
    """
    Download a Twilio recording and transcribe it with Deepgram.

    Deepgram is used over Twilio's built-in transcription because:
      - Much higher accuracy (especially Nigerian accents)
      - Speaker diarization — knows who said what
      - Faster turnaround
      - Cheaper at scale

    Args:
        recording_url: Twilio MP3 recording URL

    Returns:
        {
          "success":     True/False,
          "transcript":  "Full text of the call...",
          "speakers":    [{"speaker": 0, "text": "..."}, ...],
          "confidence":  0.95,
          "duration":    180,
          "error":       None or error string
        }
    """
    if not DEEPGRAM_API_KEY:
        return {
            "success":    False,
            "transcript": "",
            "error":      "DEEPGRAM_API_KEY not set",
        }

    try:
        deepgram = DeepgramClient(DEEPGRAM_API_KEY)

        # Options for transcription
        options = PrerecordedOptions(
            model="nova-2",           # Deepgram's most accurate model
            language="en",
            smart_format=True,        # Adds punctuation and formatting
            diarize=True,             # Identifies different speakers
            punctuate=True,
            utterances=True,          # Breaks into natural speech segments
        )

        # Twilio requires authentication to download recordings
        # We pass credentials so Deepgram can fetch it directly
        source = {
            "url":  recording_url,
            "auth": (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
        }

        response = deepgram.listen.prerecorded.v("1").transcribe_url(
            source, options
        )

        # Extract the full transcript
        result    = response.results
        channel   = result.channels[0].alternatives[0]
        transcript = channel.transcript
        confidence = channel.confidence

        # Extract speaker-separated utterances if diarization worked
        speakers = []
        if hasattr(result, "utterances") and result.utterances:
            for utt in result.utterances:
                speakers.append({
                    "speaker": utt.speaker,
                    "text":    utt.transcript,
                    "start":   utt.start,
                    "end":     utt.end,
                })

        return {
            "success":    True,
            "transcript": transcript,
            "speakers":   speakers,
            "confidence": confidence,
            "error":      None,
        }

    except Exception as e:
        return {
            "success":    False,
            "transcript": "",
            "speakers":   [],
            "confidence": 0,
            "error":      str(e),
        }


def extract_call_insights(
    transcript:    str,
    caller_number: str,
    duration_secs: int = 0,
) -> dict:
    """
    Send the transcript to Claude and extract structured insights.

    This is what turns a raw transcript into memory-ready intelligence.
    Claude reads the conversation and identifies everything the agent
    needs to know to update Jude's second brain.

    Args:
        transcript:    Full call transcript text
        caller_number: Who called
        duration_secs: How long the call lasted

    Returns:
        {
          "caller_name":     "Mr Emeka Obi",
          "summary":         "2-line summary of the call",
          "topics":          ["property viewing", "price negotiation"],
          "promises_made":   ["Send property fact sheet by Friday"],
          "action_items":    ["Book viewing for Thursday 2PM", "Send fact sheet"],
          "sentiment":       "positive" | "neutral" | "negative",
          "follow_up":       True/False,
          "follow_up_by":    "Thursday" or None,
          "client_facts":    ["Prefers waterfront", "Budget is 50M"],
          "significance":    "high" | "medium" | "low",
          "telegram_summary": "Formatted summary for Jude's Telegram"
        }
    """
    if not ANTHROPIC_API_KEY:
        # No API key — return basic summary
        return {
            "caller_name":      caller_number,
            "summary":          "Call recorded. API key needed for full analysis.",
            "topics":           [],
            "promises_made":    [],
            "action_items":     [],
            "sentiment":        "neutral",
            "follow_up":        False,
            "follow_up_by":     None,
            "client_facts":     [],
            "significance":     "medium",
            "telegram_summary": (
                f"📞 Call from {caller_number}\n"
                f"Duration: {duration_secs // 60}m {duration_secs % 60}s\n"
                f"Add ANTHROPIC_API_KEY for full analysis."
            ),
        }

    duration_str = f"{duration_secs // 60}m {duration_secs % 60}s"

    prompt = f"""
You are analyzing a phone call transcript for Jude, a Lagos real estate operator.

Caller number: {caller_number}
Call duration: {duration_str}

TRANSCRIPT:
{transcript}

Extract the following and return ONLY a JSON object with these exact keys:

{{
  "caller_name":     "Full name if mentioned, else null",
  "summary":         "2-sentence summary of what the call was about",
  "topics":          ["list", "of", "topics", "discussed"],
  "promises_made":   ["Any commitments Jude made during the call"],
  "action_items":    ["Specific tasks that need to happen after this call"],
  "sentiment":       "positive or neutral or negative",
  "follow_up":       true or false,
  "follow_up_by":    "When to follow up, e.g. Thursday, or null",
  "client_facts":    ["New facts learned about this client"],
  "significance":    "high or medium or low",
  "telegram_summary": "A clean formatted summary to send Jude on Telegram. Use emojis. Max 200 words."
}}

Be precise. Only include what was actually discussed.
If the transcript is empty or unclear, note that in the summary.
Return only the JSON object — no markdown, no explanation.
"""

    try:
        client   = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        return json.loads(raw)

    except Exception as e:
        return {
            "caller_name":      caller_number,
            "summary":          f"Transcript analysis failed: {str(e)}",
            "topics":           [],
            "promises_made":    [],
            "action_items":     [],
            "sentiment":        "neutral",
            "follow_up":        False,
            "follow_up_by":     None,
            "client_facts":     [],
            "significance":     "medium",
            "telegram_summary": (
                f"📞 Call from {caller_number}\n"
                f"Duration: {duration_str}\n"
                f"Analysis failed — check logs."
            ),
        }