#!/usr/bin/env python3
"""
opacity_bus.py  —  Discord carrier + lens seam
Kibler AI Solutions Corp.

The bus. One channel, one bot. Turns a Discord message into a Signal,
runs it through the monocle (opacity_lens), publishes the verdict +
receipt back to the same channel.

Role: this is the CARRIER, same job the iPhone does in the yard-walk
stack — capture, transceive, write the signal line. It does NOT fuse.
Barcode stays a registration anchor; the lens stack adjudicates each
signal alone. Fusion (drone_fusion) is a separate gate downstream.

One writer per surface: the bot is the only thing that writes verdicts
to the channel; inbound scans are the only thing that writes signals in.

Drop next to opacity_lens.py on the Mac Mini. Needs:
    pip install discord.py
    env: DISCORD_BOT_TOKEN, OPACITY_CHANNEL_ID
"""

import os
import json
import discord

from opacity_lens import Signal, default_monocle, look_through


# --- the frozen signal-line contract -------------------------------------
# A channel message becomes ONE Signal. Accepted inbound shapes, in order:
#
#   1. JSON:   {"kind":"barcode","payload":"036000291452","confidence":0.95}
#   2. typed:  barcode:036000291452        (confidence defaults below)
#   3. bare:   036000291452                (assumed barcode)
#
# t is ALWAYS the message's own timestamp — never trusted from the payload,
# so the debounce lens reads real arrival time. fingerprint is left empty;
# Signal.__post_init__ stamps it. This is the seam: anything that can write
# one of these three shapes can write to the gate.

DEFAULT_CONFIDENCE = 0.9


def parse_signal(content: str, t: float):
    content = content.strip()
    if not content:
        return None

    # shape 1: JSON
    if content.startswith("{"):
        try:
            d = json.loads(content)
            return Signal(
                kind=str(d["kind"]),
                payload=d["payload"],
                confidence=float(d.get("confidence", DEFAULT_CONFIDENCE)),
                t=t,
            )
        except (ValueError, KeyError, TypeError):
            return None

    # shape 2: typed  kind:payload
    if ":" in content:
        kind, _, payload = content.partition(":")
        kind = kind.strip().lower()
        if kind in ("barcode", "doppler"):
            val = payload.strip()
            if kind == "doppler":
                try:
                    val = float(val)
                except ValueError:
                    return None
            return Signal(kind=kind, payload=val,
                          confidence=DEFAULT_CONFIDENCE, t=t)

    # shape 3: bare — assume a barcode scan
    return Signal(kind="barcode", payload=content,
                  confidence=DEFAULT_CONFIDENCE, t=t)


def verdict_line(result: dict) -> str:
    """One-line human verdict for the channel, from look_through output."""
    sig = result["signals"][0]
    fp = sig["fingerprint"]
    if sig["survived"]:
        return (f"✅ `{fp}` {sig['kind']} → "
                f"**{sig['final_state']}** (intensity {sig['final_intensity']})")
    return (f"⛔ `{fp}` {sig['kind']} → "
            f"**BLOCKED** by {sig['blocked_by']}")


# --- the carrier ----------------------------------------------------------

CHANNEL_ID = int(os.environ.get("OPACITY_CHANNEL_ID", "0"))
TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
monocle = default_monocle()


@client.event
async def on_ready():
    print(f"bus up as {client.user} — watching channel {CHANNEL_ID}")


@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return                          # never adjudicate our own verdicts
    if CHANNEL_ID and message.channel.id != CHANNEL_ID:
        return                          # one channel, one bus

    sig = parse_signal(message.content, message.created_at.timestamp())
    if sig is None:
        return                          # not signal-shaped; ignore

    result = look_through([sig], monocle)
    await message.channel.send(verdict_line(result))


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("set DISCORD_BOT_TOKEN")
    client.run(TOKEN)
