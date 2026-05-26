#!/usr/bin/env python3
"""
OpacityChunk - clean, inspectable text chunking for AI pipelines.
Kibler AI Solutions Corp.

What it does, in one line:
  Messy text in -> clean, auditable chunks out, with a health report you can SEE.

Why it exists:
  Most chunkers are a black box. You hand them a document, they hand back
  pieces, and you have no idea what got split badly, what got duplicated,
  or what got dropped. This tool refuses to be a black box. Every chunk
  comes with a receipt: where it came from, how dense it is, and whether
  the chunker is confident the boundary was clean.

This is the PUBLIC-FACING chunk discipline. It is deliberately simple and
inspectable. It does not contain the internal allocation logic.
"""

import re
import json
import hashlib
from dataclasses import dataclass, asdict
from typing import List


@dataclass
class Chunk:
    """A single clean chunk, with its receipt attached.

    Every field here is a 'receipt' line - something a human can inspect
    to trust that the chunk is clean, instead of taking it on faith.
    """
    index: int            # which chunk number this is, in order
    text: str             # the actual chunk content
    char_count: int       # how big it is, in characters
    word_count: int       # how big it is, in words
    boundary: str         # how this chunk ended: 'paragraph', 'sentence', or 'hard-cut'
    density: float        # words per sentence - a rough 'how packed' score
    fingerprint: str      # short hash, so you can detect duplicate chunks
    clean_boundary: bool  # True if we ended on a natural break, not mid-thought


def _fingerprint(text: str) -> str:
    """Make a short, stable fingerprint of a chunk.

    We use this so that if the same chunk appears twice (duplication is a
    very common silent failure in chunking), you can SEE it - two chunks
    with the same fingerprint means duplicated content.
    """
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:12]


def _split_sentences(text: str) -> List[str]:
    """Split text into sentences in a simple, transparent way.

    We are deliberately NOT using a heavy NLP library here. The whole
    selling point of this tool is that you can read the logic and trust it.
    A regex on sentence-ending punctuation is something a buyer can audit
    in five seconds. That trust IS the product.
    """
    # Split after . ! or ? when followed by whitespace and a capital/quote/digit.
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z0-9"\'\'])', text.strip())
    return [p.strip() for p in parts if p.strip()]


def chunk_text(raw: str, target_chars: int = 800) -> List[Chunk]:
    """Turn messy text into clean, receipt-bearing chunks.

    The strategy, in plain English:
      1. First try to break on paragraph boundaries (double newlines).
         These are the cleanest, most natural breaks.
      2. If a paragraph is too big, break it on sentence boundaries.
      3. Only as a last resort do we hard-cut mid-sentence, and when we
         do, we MARK it (clean_boundary = False) so you know.

    target_chars is the rough size you want each chunk to be. We treat it
    as a target, not a hard rule, because forcing exact sizes is what
    causes mid-thought cuts in the first place.
    """
    # Normalize whitespace first so the input is predictable.
    # This is the 'no surprises' step - we make the mess regular before we cut.
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = [p.strip() for p in raw.split("\n\n") if p.strip()]

    chunks: List[Chunk] = []
    buffer = ""
    buffer_boundary = "paragraph"

    def flush(boundary_type: str):
        """Push whatever is in the buffer out as a finished chunk, with its receipt."""
        nonlocal buffer
        text = buffer.strip()
        if not text:
            return
        sentences = _split_sentences(text)
        words = text.split()
        density = round(len(words) / max(len(sentences), 1), 1)
        chunks.append(Chunk(
            index=len(chunks),
            text=text,
            char_count=len(text),
            word_count=len(words),
            boundary=boundary_type,
            density=density,
            fingerprint=_fingerprint(text),
            clean_boundary=(boundary_type != "hard-cut"),
        ))
        buffer = ""

    for para in paragraphs:
        # If this whole paragraph fits in the buffer, keep stacking.
        if len(buffer) + len(para) + 2 <= target_chars:
            buffer = (buffer + "\n\n" + para).strip()
            buffer_boundary = "paragraph"
            continue

        # The paragraph doesn't fit. Flush what we have first.
        if buffer:
            flush(buffer_boundary)

        # If the paragraph itself fits in one chunk, it becomes one chunk.
        if len(para) <= target_chars:
            buffer = para
            buffer_boundary = "paragraph"
            flush("paragraph")
            continue

        # The paragraph is too big on its own. Break it by sentences.
        for sent in _split_sentences(para):
            if len(buffer) + len(sent) + 1 <= target_chars:
                buffer = (buffer + " " + sent).strip()
                buffer_boundary = "sentence"
            else:
                if buffer:
                    flush("sentence")
                # A single sentence longer than target_chars: hard-cut it,
                # and MARK the cut so the receipt tells the truth.
                while len(sent) > target_chars:
                    buffer = sent[:target_chars]
                    sent = sent[target_chars:]
                    flush("hard-cut")
                buffer = sent
                buffer_boundary = "sentence"

    # Flush whatever is left at the very end.
    if buffer:
        flush(buffer_boundary)

    return chunks


def health_report(chunks: List[Chunk]) -> dict:
    """Produce a plain-language health report on the chunk set.

    This is the 'opacity lens' part - the whole point is that you can SEE
    the quality of the chunking instead of trusting it blindly. These four
    numbers are deliberately the RATML-family health metrics, surfaced in
    a form anyone can read:

      recoverability - can you trust the boundaries? (clean vs hard-cut)
      coherence      - are chunks consistent in size, or wildly uneven?
      load           - how much total content, how many pieces
      density        - how packed the language is on average
    """
    if not chunks:
        return {"error": "no chunks produced - was the input empty?"}

    total = len(chunks)
    hard_cuts = sum(1 for c in chunks if not c.clean_boundary)
    fingerprints = [c.fingerprint for c in chunks]
    duplicates = len(fingerprints) - len(set(fingerprints))
    sizes = [c.char_count for c in chunks]
    avg_size = sum(sizes) / total
    # spread = how uneven the chunk sizes are (0 = perfectly even)
    spread = round((max(sizes) - min(sizes)) / max(avg_size, 1), 2)
    avg_density = round(sum(c.density for c in chunks) / total, 1)

    # Recoverability as a clean percentage - the headline trust number.
    recoverability = round(100 * (total - hard_cuts) / total, 1)

    return {
        "total_chunks": total,
        "recoverability_pct": recoverability,   # higher = cleaner boundaries
        "clean_boundaries": total - hard_cuts,
        "hard_cuts": hard_cuts,                  # mid-thought cuts you should review
        "duplicate_chunks": duplicates,         # silent failure made visible
        "avg_chunk_chars": round(avg_size),
        "size_spread": spread,                  # lower = more consistent
        "avg_density_words_per_sentence": avg_density,
        "verdict": (
            "CLEAN - safe to send to your model"
            if recoverability >= 90 and duplicates == 0
            else "REVIEW - some boundaries or duplicates need a look"
        ),
    }


def process(raw: str, target_chars: int = 800) -> dict:
    """The one call most people will use: text in, chunks + report out."""
    chunks = chunk_text(raw, target_chars=target_chars)
    return {
        "report": health_report(chunks),
        "chunks": [asdict(c) for c in chunks],
    }


if __name__ == "__main__":
    import sys
    # Read from a file argument, or from stdin, or run the built-in demo.
    if len(sys.argv) > 1:
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            raw = f.read()
    elif not sys.stdin.isatty():
        raw = sys.stdin.read()
    else:
        raw = (
            "Guardian is a constitutional substrate. It does not override the human.\n\n"
            "Most chunkers are a black box. You hand them a document and you cannot "
            "see what they did to it. This tool refuses that. Every chunk carries a "
            "receipt so you can trust it before it reaches your model. That trust is "
            "the whole product. " * 6
        )
    result = process(raw)
    print(json.dumps(result, indent=2))
