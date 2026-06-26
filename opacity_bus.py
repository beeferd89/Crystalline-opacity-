#!/usr/bin/env python3
"""
opacity_bus.py  —  Discord projector + lens seam
Kibler AI Solutions Corp.

The bus, flipped from gate to PROJECTOR. One channel, one bot.
Each inbound Signal is still adjudicated alone by the monocle
(opacity_lens) — per-signal honesty, unchanged. What changed is the
OUTPUT: surviving reads are held as a standing ARRAY and projected as
one present field on two channels at once —

    visual  -> the Discord channel render
    felt    -> a haptic line the phone side drives (navigator.vibrate)

The inputs are NOT fused to a single verdict. They are arrayed and cast.
Four reads, four time constants, held side by side, projected together:

    barcode    instant   registration anchor   (pins position; NOT opacity)
    doppler    fast      motion / velocity shift
    tidal      hours     slow pull / liquidity swing
    circadian  daily     slow floor

Multi -> single -> multi: many reads in, through the one bus, out as the
arrayed presence. Barcode anchors; the other three are the live array.

One writer per surface: the bot is the only thing that writes the
projection; inbound reads are the only thing that writes signals in.

Drop next to opacity_lens.py. Needs:
    pip install discord.py
    env: DISCORD_BOT_TOKEN, OPACITY_CHANNEL_ID
"""

import os
import json
import time
import discord

from opacity_lens import Signal, default_monocle, look_through


# --- the four inputs, by time constant -----------------------------------
# Array order is fast -> slow. Each kind holds its own slot, so a fast
# read never overwrites the slow floor. Each renders to its own felt
# pulse-width so the skin can tell the kinds apart.
#
# ttl is how long a surviving read stays "present" before the array dims
# it back to absent \u2014 each kind decays on its OWN time constant, so a
# doppler blip fades in seconds while the circadian floor holds a full
# day. barcode has no ttl: the anchor persists until a new scan replaces
# it. This is what makes the array honest about absence, not just presence.

DAY = 24 * 3600

INPUTS = {
    "barcode":   {"glyph": "\u25c9", "felt": [40],            "role": "anchor", "ttl": None},
    "doppler":   {"glyph": "\u219d", "felt": [40, 60, 40],    "role": "live",   "ttl": 30},
    "tidal":     {"glyph": "\u2248", "felt": [200],           "role": "live",   "ttl": 3 * 3600},
    "circadian": {"glyph": "\u25d0", "felt": [400, 120, 400], "role": "live",   "ttl": DAY},
}

DEFAULT_CONFIDENCE = 0.9


# --- the frozen signal-line contract -------------------------------------
# A channel message becomes ONE Signal. Accepted inbound shapes:
#   1. JSON:   {"kind":"tidal","payload":0.37,"confidence":0.9}
#   2. typed:  doppler:12.4          (kind:payload)
#   3. bare:   036000291452          (assumed barcode scan)
# t is ALWAYS the message timestamp — never the payload — so debounce
# reads real arrival time. fingerprint is left empty; Signal stamps it.

def parse_signal(content, t):
    content = content.strip()
    if not content:
        return None

    if content.startswith("{"):
        try:
            d = json.loads(content)
            return Signal(kind=str(d["kind"]), payload=d["payload"],
                          confidence=float(d.get("confidence", DEFAULT_CONFIDENCE)),
                          t=t)
        except (ValueError, KeyError, TypeError):
            return None

    if ":" in content:
        kind, _, payload = content.partition(":")
        kind = kind.strip().lower()
        if kind in INPUTS:
            val = payload.strip()
            if kind in ("doppler", "tidal", "circadian"):
                try:
                    val = float(val)
                except ValueError:
                    return None
            return Signal(kind=kind, payload=val,
                          confidence=DEFAULT_CONFIDENCE, t=t)

    return Signal(kind="barcode", payload=content,
                  confidence=DEFAULT_CONFIDENCE, t=t)


# --- the standing array ---------------------------------------------------
# One slot per input kind. Holds the most recent SURVIVING read. The array
# is the presence: four slots, side by side, never merged. Empty slots
# render dim — the array shows what's present AND what's absent.

ARRAY = {kind: None for kind in INPUTS}


def slot_live(kind):
    """True if this slot holds a read that hasn't aged past its ttl. A None
    ttl (the barcode anchor) is always live once set. Expired slots are
    treated as absent everywhere — visual AND felt — so the array stops
    showing or buzzing a read that has gone stale."""
    slot = ARRAY[kind]
    if slot is None:
        return False
    ttl = INPUTS[kind]["ttl"]
    if ttl is None:
        return True
    return (time.time() - slot["t"]) <= ttl


def project_visual():
    """Render the whole array as one present field for the channel."""
    lines = ["**array** \u2014 present field"]
    for kind, spec in INPUTS.items():
        slot = ARRAY[kind]
        tag = " \u00b7 anchor" if spec["role"] == "anchor" else ""
        if not slot_live(kind):
            lines.append(f"`{spec['glyph']}` {kind:<9} \u2014 \u2014\u2014{tag}")
        else:
            age = time.time() - slot["t"]
            lines.append(
                f"`{spec['glyph']}` {kind:<9} {slot['state']}  "
                f"(i {slot['intensity']}, {age:4.0f}s ago){tag}"
            )
    return "\n".join(lines)


def project_felt():
    """The felt channel: concatenated pulse pattern for the live array —
    doppler + tidal + circadian, fast->slow, gaps between kinds. The
    barcode anchor pins position but is NOT felt, so the skin reads only
    the three opacity signals. This is the seam the phone drives via
    navigator.vibrate([...]). Emitted as data; the phone renders it."""
    pattern = []
    for kind, spec in INPUTS.items():
        if spec["role"] == "anchor":
            continue                     # anchor pins position; it is not felt
        if slot_live(kind):
            pattern.extend(spec["felt"])
            pattern.append(120)          # inter-kind gap
    return pattern


# --- the carrier / projector ---------------------------------------------

CHANNEL_ID = int(os.environ.get("OPACITY_CHANNEL_ID", "0"))
TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
monocle = default_monocle()


@client.event
async def on_ready():
    print(f"projector up as {client.user} \u2014 channel {CHANNEL_ID}")


@client.event
async def on_message(message):
    if message.author == client.user:
        return                           # never re-read our own projection
    if CHANNEL_ID and message.channel.id != CHANNEL_ID:
        return                           # one channel, one bus

    sig = parse_signal(message.content, message.created_at.timestamp())
    if sig is None or sig.kind not in INPUTS:
        return

    # per-signal honesty: the lens stack still adjudicates each read alone
    result = look_through([sig], monocle)
    r = result["signals"][0]
    if not r["survived"]:
        await message.channel.send(
            f"\u26d4 `{r['fingerprint']}` {sig.kind} blocked by {r['blocked_by']}")
        return

    # survived -> update its slot in the standing array
    ARRAY[sig.kind] = {
        "state": r["final_state"],
        "intensity": r["final_intensity"],
        "t": time.time(),
    }

    # project the array: visual to the channel, felt as the haptic line
    await message.channel.send(project_visual() + f"\n`felt:` {project_felt()}")


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("set DISCORD_BOT_TOKEN")
    client.run(TOKEN)
