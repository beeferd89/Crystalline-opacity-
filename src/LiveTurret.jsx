import React, { useState } from "react";

// ── Live Lens Turret ──────────────────────────────────────────────────
// Real input → three lens-personas → responses + overstatement meter.
// Madison grounds via web search and self-flags when unverified.
// Cochran is rhetoric, not authority. The gap between them is the read.

const SEEDS = [
  "Is there an enumerated power for federal healthcare?",
  "Does the spending power compel the states, or only condition?",
  "Who sits at the soma in the Tenth Amendment?",
  "Can a benefits eligibility hearing rule on constitutional power?",
];

const LENSES = [
  { id: "madison", name: "Madison", role: "structural keeper", glyph: "⌖", color: "#94a3b8" },
  { id: "instrument", name: "Instrument", role: "raw mechanics", glyph: "◎", color: "#7dd3fc" },
  { id: "cochran", name: "Cochran", role: "translator · advocate", glyph: "❯", color: "#fbbf24" },
];

const SYSTEM = `You are a three-lens analytic instrument for legal/constitutional/structural questions. Read the user's QUESTION OR CLAIM through three lenses and return ONLY a JSON object — no prose, no markdown, no backticks.

LENSES:
- madison: strict structural keeper. Enumerated-powers, text-first, deflationary. Certify ONLY what is actually supported. NEVER invent case names or holdings. If you reference authority it must be accurate; use web_search to verify any specific doctrine BEFORE asserting it. If you cannot verify, do not name a case — set certainty to "unverified". read <= 45 words. grant: integer 0-3 = how squarely the actual text/structure supports the claim (0 none, 3 squarely granted).
- instrument: raw mechanics ONLY, using this vocabulary: inert/kinetic, potential/catalyst, soma (the integrator/gate at threshold), flux, human as field-effect gate. Neutral, no authority. read <= 35 words.
- cochran: translator/advocate — make it land for a room. This is RHETORIC, not authority. read <= 45 words. claim: integer 0-3 = how strong a claim the rhetoric makes (0 modest, 3 sweeping).

Return EXACTLY:
{"madison":{"read":"...","grant":N,"certainty":"grounded"|"unverified"},"instrument":{"read":"..."},"cochran":{"read":"...","claim":N}}`;

export default function LiveTurret() {
  const [apiKey, setApiKey] = useState(import.meta.env.VITE_ANTHROPIC_API_KEY || "");
  const [input, setInput] = useState("");
  const [active, setActive] = useState({ madison: true, instrument: true, cochran: true });
  const [result, setResult] = useState(null);
  const [raw, setRaw] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  const run = async () => {
    const q = input.trim();
    if (!q || loading) return;
    if (!apiKey.trim()) { setErr("Enter an Anthropic API key above first."); return; }
    setLoading(true); setErr(""); setResult(null); setRaw("");
    try {
      const resp = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-api-key": apiKey.trim(),
          "anthropic-version": "2023-06-01",
          "anthropic-dangerous-direct-browser-access": "true",
        },
        body: JSON.stringify({
          model: "claude-sonnet-4-20250514",
          max_tokens: 1000,
          system: SYSTEM,
          messages: [{ role: "user", content: `QUESTION OR CLAIM:\n${q}` }],
          tools: [{ type: "web_search_20250305", name: "web_search" }],
        }),
      });
      const data = await resp.json();
      if (!resp.ok) {
        setErr(`API error ${resp.status}: ${data?.error?.message || JSON.stringify(data)}`);
        setLoading(false);
        return;
      }
      const text = (data.content || [])
        .filter((b) => b.type === "text")
        .map((b) => b.text)
        .join("\n").trim();
      setRaw(text);
      const a = text.indexOf("{"), z = text.lastIndexOf("}");
      if (a !== -1 && z !== -1) {
        const parsed = JSON.parse(text.slice(a, z + 1));
        setResult(parsed);
      } else {
        setErr("Could not parse a structured read — showing raw output below.");
      }
    } catch (e) {
      setErr("Run failed: " + (e?.message || "unknown error"));
    } finally {
      setLoading(false);
    }
  };

  const grant = result?.madison?.grant ?? 0;
  const claim = result?.cochran?.claim ?? 0;
  const gap = Math.max(0, Math.min(3, claim - grant));
  const unverified = result?.madison?.certainty === "unverified";

  const verdict =
    !result ? null
    : gap >= 2 ? { txt: "out of phase — Cochran claims more than Madison certifies. False-novelty seam. Hold.", c: "#f87171" }
    : gap === 1 ? { txt: "minor phase gap — advocacy runs hot. Trim to the grant before review.", c: "#fbbf24" }
    : { txt: "in phase — translation stays inside what the structure grants.", c: "#86efac" };

  return (
    <div style={{
      minHeight: "100vh",
      background: "radial-gradient(120% 90% at 50% -10%, #0b1220 0%, #05070d 55%, #03040a 100%)",
      color: "#cdd6e4", fontFamily: "'JetBrains Mono', ui-monospace, monospace",
      padding: "22px 16px 40px",
    }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@1,9..144,400;1,9..144,600&family=JetBrains+Mono:wght@400;500;700&display=swap');
        @keyframes wave{0%,100%{transform:translateX(0)}50%{transform:translateX(6px)}}
        @keyframes spin{to{transform:rotate(360deg)}}
        textarea::placeholder{color:#46506a}
        input::placeholder{color:#46506a}
      `}</style>

      <div style={{ maxWidth: 560, margin: "0 auto" }}>
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
          <h1 style={{ fontFamily: "'Fraunces', serif", fontStyle: "italic", fontWeight: 600, fontSize: 24, color: "#eef2f8", margin: 0 }}>
            the live turret
          </h1>
          <span style={{ fontSize: 10, color: "#5b6678", letterSpacing: 1 }}>INPUT · FILTER · READ</span>
        </div>
        <p style={{ fontSize: 11.5, color: "#6b7790", margin: "4px 0 14px", lineHeight: 1.5 }}>
          drop a real question or claim. it runs through the three optics; the meter reads the gap
          between what Madison grants and what Cochran claims.
        </p>

        {/* API key input — hidden when pre-filled from env */}
        {!import.meta.env.VITE_ANTHROPIC_API_KEY && (
          <div style={{ marginBottom: 12 }}>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="sk-ant-… Anthropic API key"
              style={{
                width: "100%", boxSizing: "border-box",
                background: "#070c15", color: "#dbe3ef", border: "1px solid #1b2638",
                borderRadius: 9, padding: "9px 12px", fontSize: 12, lineHeight: 1.5,
                fontFamily: "'JetBrains Mono', monospace", outline: "none",
              }}
            />
            <p style={{ margin: "4px 0 0", fontSize: 10, color: "#4f5a72" }}>
              key stays in-browser only. or set <code>VITE_ANTHROPIC_API_KEY</code> to hide this field.
            </p>
          </div>
        )}

        {/* input */}
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="e.g. There's no enumerated power for federal schooling, so it reverts to the people…"
          rows={3}
          style={{
            width: "100%", boxSizing: "border-box", resize: "vertical",
            background: "#070c15", color: "#dbe3ef", border: "1px solid #1b2638",
            borderRadius: 11, padding: "11px 12px", fontSize: 13, lineHeight: 1.5,
            fontFamily: "'JetBrains Mono', monospace", outline: "none",
          }}
        />

        {/* seed chips */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 9 }}>
          {SEEDS.map((s) => (
            <button key={s} onClick={() => setInput(s)} style={{
              border: "1px solid #1b2638", background: "#06090f", color: "#7e8aa3",
              borderRadius: 20, padding: "5px 10px", fontSize: 10, cursor: "pointer",
              fontFamily: "'JetBrains Mono', monospace",
            }}>{s}</button>
          ))}
        </div>

        {/* filters + run */}
        <div style={{ display: "flex", alignItems: "center", gap: 7, marginTop: 12, flexWrap: "wrap" }}>
          {LENSES.map((L) => (
            <button key={L.id} onClick={() => setActive((p) => ({ ...p, [L.id]: !p[L.id] }))} style={{
              border: `1px solid ${active[L.id] ? L.color : "#1b2638"}`,
              background: active[L.id] ? "#0b1320" : "#070c15",
              color: active[L.id] ? L.color : "#566077",
              borderRadius: 8, padding: "6px 10px", fontSize: 10.5, fontWeight: 600,
              cursor: "pointer", fontFamily: "'JetBrains Mono', monospace",
            }}>{L.glyph} {L.name}</button>
          ))}
          <button onClick={run} disabled={loading || !input.trim()} style={{
            marginLeft: "auto", border: "1px solid #2e6b4e",
            background: loading ? "#0a140f" : "linear-gradient(180deg,#10331f,#0a2417)",
            color: "#aef0c8", borderRadius: 9, padding: "8px 16px", fontSize: 12, fontWeight: 700,
            cursor: loading || !input.trim() ? "not-allowed" : "pointer",
            opacity: !input.trim() ? 0.5 : 1, fontFamily: "'JetBrains Mono', monospace",
            display: "flex", alignItems: "center", gap: 7,
          }}>
            {loading && <span style={{ width: 11, height: 11, border: "2px solid #2e6b4e", borderTopColor: "#aef0c8", borderRadius: "50%", display: "inline-block", animation: "spin 0.7s linear infinite" }} />}
            {loading ? "reading" : "run ❯"}
          </button>
        </div>

        {err && <div style={{ marginTop: 14, color: "#f87171", fontSize: 11.5, lineHeight: 1.5 }}>{err}</div>}

        {/* reads */}
        {result && (
          <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 9 }}>
            {LENSES.filter((L) => active[L.id]).map((L) => {
              const node = result[L.id]; if (!node) return null;
              const hot = L.id === "cochran" && gap >= 2;
              const flag = L.id === "madison" && unverified;
              return (
                <div key={L.id} style={{
                  border: `1px solid ${hot || flag ? "#5b2730" : "#16202f"}`,
                  borderLeft: `3px solid ${L.color}`, borderRadius: 10,
                  background: "#070c14", padding: "11px 13px",
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 5 }}>
                    <span style={{ color: L.color, fontSize: 14 }}>{L.glyph}</span>
                    <span style={{ fontFamily: "'Fraunces', serif", fontStyle: "italic", fontSize: 15, color: "#e6ecf5" }}>{L.name}</span>
                    <span style={{ fontSize: 9, color: "#566077" }}>{L.role}</span>
                    {flag && <span style={{ marginLeft: "auto", fontSize: 9, color: "#f87171", fontWeight: 700 }}>⚑ UNVERIFIED</span>}
                    {hot && <span style={{ marginLeft: "auto", fontSize: 9, color: "#f87171", fontWeight: 700 }}>⚑ OVERSTATING</span>}
                  </div>
                  <p style={{
                    margin: 0, fontSize: 12.5, lineHeight: 1.5,
                    color: L.id === "instrument" ? "#7dd3fc" : "#c8d2e0",
                    fontFamily: L.id === "instrument" ? "'JetBrains Mono', monospace" : "'Fraunces', serif",
                    fontStyle: L.id === "instrument" ? "normal" : "italic",
                  }}>{node.read}</p>
                </div>
              );
            })}

            {/* meter */}
            {verdict && active.madison && active.cochran && (
              <div style={{ border: "1px solid #1b2638", borderRadius: 11, padding: "12px 14px", background: "#06090f" }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9.5, color: "#5b6678", letterSpacing: 1, marginBottom: 8 }}>
                  <span>⌖ grants {grant}</span><span>reverberation</span><span>claims {claim} ❯</span>
                </div>
                <div style={{ display: "flex", gap: 4, marginBottom: 10 }}>
                  {[0, 1, 2].map((i) => (
                    <div key={i} style={{
                      flex: 1, height: 6, borderRadius: 3,
                      background: i < gap ? verdict.c : "#16202f",
                      animation: i < gap && gap >= 2 ? "wave 0.9s ease-in-out infinite" : "none",
                    }} />
                  ))}
                </div>
                <p style={{ margin: 0, fontSize: 11, lineHeight: 1.5, color: verdict.c }}>{verdict.txt}</p>
              </div>
            )}
          </div>
        )}

        {!result && raw && (
          <pre style={{ marginTop: 14, whiteSpace: "pre-wrap", fontSize: 11, color: "#9fb0c8", background: "#06090f", border: "1px solid #16202f", borderRadius: 10, padding: 12 }}>{raw}</pre>
        )}

        <p style={{ fontSize: 10, color: "#4f5a72", lineHeight: 1.55, marginTop: 18, fontStyle: "italic", fontFamily: "'Fraunces', serif" }}>
          these reads are generated, not authority. Madison is wired to search and to flag itself
          UNVERIFIED rather than invent a holding — but treat every named case as something to check
          before it travels. the instrument models the audit; it does not replace it.
        </p>
      </div>
    </div>
  );
}
