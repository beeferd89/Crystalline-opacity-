import React, { useState } from "react";

// ── Guardian Lens · rigor = strength ──────────────────────────────────
// Each glass returns a read + rigor score (0-3). Rigor modulates the
// read's visual weight AND gates fire: the WEAKEST active glass's rigor
// is the field's ceiling. Low rigor → quiet, held. High rigor → kinetic.
// Catalyst lowers the bar; rigor decides whether the bar is reached.

const AGENTS = [
  { id: "direct", name: "Direct", glyph: "◆", color: "#4ade80",
    bound: "no cruelty · no overstatement" },
  { id: "curious", name: "Curious", glyph: "◇", color: "#a78bfa",
    bound: "questions must be load-bearing" },
  { id: "analytical", name: "Analytical", glyph: "⬡", color: "#60a5fa",
    bound: "no invented authority" },
  { id: "nurturing", name: "Nurturing", glyph: "◉", color: "#f472b6",
    bound: "care must not erase a real error" },
  { id: "precise", name: "Precise", glyph: "■", color: "#fbbf24",
    bound: "states uncertainty plainly" },
  { id: "adaptive", name: "Adaptive", glyph: "⬟", color: "#34d399",
    bound: "must not drift into validating all" },
];

const SYSTEM = `You are GUARDIAN LENS — a bounded multi-agent analytic instrument where RIGOR is the strength of the answer.

For EACH active agent, return:
- read (<=35 words) in that agent's disposition, honoring its hard boundary.
- rigor: integer 0..3 — how well-grounded THIS specific read is. Score honestly:
  * 3 = grounded in verifiable structure/text/fact, no leap unsupported
  * 2 = mostly grounded, one minor inferential step
  * 1 = directional / partial / one significant unsupported step
  * 0 = speculative, unverified, or leaning on rhetoric > evidence
  IMPORTANT: rigor scoring must be conservative. Score what is actually earned, not what is asserted. A confident-sounding read with no grounding is rigor 0 or 1, never 3.
- evidence (<=18 words): the specific basis for the rigor score — what grounds the read, or what's missing.

Hard agent boundaries:
- direct: blunt, no hedging. BOUND: no cruelty, no overstatement.
- curious: ends on one sharpest question. BOUND: load-bearing only.
- analytical: decompose premises → conclusion. BOUND: never invent authority; use web_search for any specific fact/holding.
- nurturing: protective framing. BOUND: warmth must NOT erase a real error.
- precise: exact, narrow, defined terms. BOUND: state uncertainty.
- adaptive: synthesize. BOUND: do not validate everything.

ALWAYS also return:
- fallacies: array of {name, locus, severity:"low"|"med"|"high"}. Empty if none. Never invent.
- structure: {grant: 0-3, certainty:"grounded"|"unverified", note (<=20 words)}.
- advocacy: {claim: 0-3} — strength of the most persuasive framing.
- gate: {state:"GO"|"HOLD"|"STOP", why (<=22 words)}.
  Rules: STOP = fatal fallacy OR all active agents rigor 0.
  HOLD = any high-severity fallacy, OR minimum agent rigor < 2, OR advocacy claim - structure grant >= 2.
  GO = no high fallacy AND minimum rigor >= 2 AND polarization < 2.

Return ONLY JSON, no prose, no backticks:
{"agents":{"<id>":{"read":"...","rigor":N,"evidence":"..."}},"fallacies":[],"structure":{"grant":N,"certainty":"...","note":"..."},"advocacy":{"claim":N},"gate":{"state":"...","why":"..."}}`;

export default function GuardianLens() {
  const [apiKey, setApiKey] = useState(import.meta.env.VITE_ANTHROPIC_API_KEY || "");
  const [sel, setSel] = useState({ direct: true, analytical: true, precise: true, curious: false, nurturing: false, adaptive: false });
  const [fieldGate, setFieldGate] = useState(true);
  const [input, setInput] = useState("");
  const [res, setRes] = useState(null);
  const [raw, setRaw] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  const activeIds = AGENTS.filter((a) => sel[a.id]).map((a) => a.id);

  const run = async () => {
    const q = input.trim();
    if (!q || loading || activeIds.length === 0) return;
    if (!apiKey.trim()) { setErr("Enter an Anthropic API key above first."); return; }
    setLoading(true); setErr(""); setRes(null); setRaw("");
    try {
      const r = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-api-key": apiKey.trim(),
          "anthropic-version": "2023-06-01",
          "anthropic-dangerous-direct-browser-access": "true",
        },
        body: JSON.stringify({
          model: "claude-sonnet-4-20250514",
          max_tokens: 1400,
          system: SYSTEM,
          messages: [{ role: "user", content: `ACTIVE agents: ${activeIds.join(", ")}\n\nPROMPT:\n${q}` }],
          tools: [{ type: "web_search_20250305", name: "web_search" }],
        }),
      });
      const data = await r.json();
      if (!r.ok) {
        setErr(`API error ${r.status}: ${data?.error?.message || JSON.stringify(data)}`);
        setLoading(false);
        return;
      }
      const text = (data.content || []).filter((b) => b.type === "text").map((b) => b.text).join("\n").trim();
      setRaw(text);
      const a = text.indexOf("{"), z = text.lastIndexOf("}");
      if (a !== -1 && z !== -1) setRes(JSON.parse(text.slice(a, z + 1)));
      else setErr("Couldn't parse a structured reply.");
    } catch (e) { setErr("Run failed: " + (e?.message || "unknown")); }
    finally { setLoading(false); }
  };

  const grant = res?.structure?.grant ?? 0;
  const claim = res?.advocacy?.claim ?? 0;
  const spread = Math.max(0, Math.min(3, claim - grant));
  const unverified = res?.structure?.certainty === "unverified";

  const rigors = res?.agents ? Object.values(res.agents).map((a) => a.rigor ?? 0) : [];
  const minRigor = rigors.length ? Math.min(...rigors) : 0;
  const avgRigor = rigors.length ? rigors.reduce((s, v) => s + v, 0) / rigors.length : 0;

  const baseState = res?.gate?.state || "—";
  const held = fieldGate && baseState === "GO";
  const shown = held ? "GO · HELD" : baseState;
  const tone = baseState === "GO" ? "#86efac" : baseState === "HOLD" ? "#fbbf24" : baseState === "STOP" ? "#f87171" : "#5b6678";

  const strength = (r) => ({
    fontWeight: r >= 3 ? 600 : r === 2 ? 500 : 400,
    opacity: r >= 3 ? 1 : r === 2 ? 0.92 : r === 1 ? 0.7 : 0.5,
    fontStyle: r <= 1 ? "italic" : "normal",
  });
  const rigorColor = (r) => r >= 3 ? "#86efac" : r === 2 ? "#fbbf24" : r === 1 ? "#f8a071" : "#f87171";
  const rigorLabel = (r) => ["speculative", "partial", "grounded", "verified"][r] || "—";

  return (
    <div style={{ minHeight: "100vh", background: "#0b0d0c", color: "#cdd6cf", fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,500;1,9..144,500&family=JetBrains+Mono:wght@400;500;700&display=swap');
        @keyframes spin{to{transform:rotate(360deg)}}
        @keyframes glow{0%,100%{opacity:.5}50%{opacity:1}}
        textarea::placeholder{color:#3f5043}
        input::placeholder{color:#3f5043}
      `}</style>

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 16px", borderBottom: "1px solid #18211b" }}>
        <div style={{ fontFamily: "'Fraunces',serif", fontSize: 20 }}>
          <span style={{ color: "#e8efe9" }}>Guardian</span><span style={{ color: "#caa45a" }}>Lens</span>
          <span style={{ fontSize: 9, color: "#5d6b60", marginLeft: 8, letterSpacing: 2 }}>RIGOR=STRENGTH</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 11, color: "#7c8a80" }}>
          <span style={{ width: 8, height: 8, borderRadius: "50%", background: tone, animation: "glow 2s ease-in-out infinite" }} />
          Live
        </div>
      </div>

      <div style={{ maxWidth: 600, width: "100%", margin: "0 auto", padding: 16, boxSizing: "border-box" }}>

        {/* API key — hidden when pre-filled from env */}
        {!import.meta.env.VITE_ANTHROPIC_API_KEY && (
          <div style={{ marginBottom: 14 }}>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="sk-ant-… Anthropic API key"
              style={{
                width: "100%", boxSizing: "border-box",
                background: "#0e1210", color: "#dbe3dd", border: "1px solid #1b241d",
                borderRadius: 9, padding: "9px 12px", fontSize: 12,
                fontFamily: "'JetBrains Mono', monospace", outline: "none",
              }}
            />
            <p style={{ margin: "4px 0 0", fontSize: 10, color: "#4a564d" }}>
              key stays in-browser only. or set <code>VITE_ANTHROPIC_API_KEY</code> to hide this field.
            </p>
          </div>
        )}

        <div style={{ fontSize: 10, letterSpacing: 3, color: "#5d6b60", marginBottom: 8 }}>CHARACTER · GLASS</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 7 }}>
          {AGENTS.map((a) => {
            const on = sel[a.id];
            return (
              <button key={a.id} onClick={() => setSel((p) => ({ ...p, [a.id]: !p[a.id] }))} style={{
                textAlign: "left", display: "flex", alignItems: "center", gap: 9,
                border: `1px solid ${on ? a.color + "88" : "#1b241d"}`,
                background: on ? a.color + "14" : "#0e1210",
                borderRadius: 10, padding: "9px 11px", cursor: "pointer",
              }}>
                <span style={{ color: a.color, fontSize: 14 }}>{a.glyph}</span>
                <span style={{ flex: 1 }}>
                  <span style={{ fontSize: 12.5, color: on ? "#e6ede7" : "#8a988c", fontWeight: 600 }}>{a.name}</span>
                  <span style={{ display: "block", fontSize: 8.5, color: "#566", marginTop: 1 }}>{a.bound}</span>
                </span>
                <span style={{ width: 7, height: 7, borderRadius: "50%", background: on ? a.color : "#28332a", boxShadow: on ? `0 0 6px ${a.color}` : "none" }} />
              </button>
            );
          })}
        </div>

        <textarea value={input} onChange={(e) => setInput(e.target.value)} rows={3}
          placeholder="drop a claim — rigor decides how loudly the lens is allowed to answer…"
          style={{ width: "100%", boxSizing: "border-box", resize: "vertical", marginTop: 14, background: "#0e1210", color: "#dbe3dd", border: "1px solid #1b241d", borderRadius: 11, padding: "11px 12px", fontSize: 13, lineHeight: 1.5, fontFamily: "'JetBrains Mono',monospace", outline: "none" }} />

        <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 11 }}>
          <button onClick={() => setFieldGate((v) => !v)} style={{
            border: `1px solid ${fieldGate ? "#caa45a88" : "#1b241d"}`, background: fieldGate ? "#1a1407" : "#0e1210",
            color: fieldGate ? "#e7c885" : "#7c8a80", borderRadius: 8, padding: "7px 11px", fontSize: 10.5, fontWeight: 600, cursor: "pointer",
          }}>⦿ field gate {fieldGate ? "engaged" : "off"}</button>
          <span style={{ fontSize: 9.5, color: "#4f5d52" }}>{activeIds.length} glass{activeIds.length === 1 ? "" : "es"}</span>
          <button onClick={run} disabled={loading || !input.trim() || !activeIds.length} style={{
            marginLeft: "auto", border: "1px solid #2e6b4e",
            background: loading ? "#0a140f" : "linear-gradient(180deg,#10331f,#0a2417)", color: "#aef0c8",
            borderRadius: 9, padding: "8px 17px", fontSize: 12, fontWeight: 700,
            cursor: loading || !input.trim() || !activeIds.length ? "not-allowed" : "pointer",
            opacity: !input.trim() || !activeIds.length ? 0.5 : 1,
            display: "flex", alignItems: "center", gap: 7,
          }}>
            {loading && <span style={{ width: 11, height: 11, border: "2px solid #2e6b4e", borderTopColor: "#aef0c8", borderRadius: "50%", animation: "spin .7s linear infinite" }} />}
            {loading ? "reading" : "run ❯"}
          </button>
        </div>

        {err && <div style={{ marginTop: 14, color: "#f87171", fontSize: 11.5 }}>{err}</div>}

        {/* gate + rigor floor */}
        {res && (
          <div style={{ marginTop: 16, border: "1px solid #18211b", borderRadius: 12, background: "#0c100e", padding: "12px 14px" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <span style={{ fontSize: 10, letterSpacing: 2, color: "#5d6b60" }}>SOMA GATE</span>
              <span style={{ fontSize: 22, fontWeight: 700, color: tone, filter: `drop-shadow(0 0 8px ${tone}55)` }}>{shown}</span>
            </div>
            <div style={{ fontSize: 11, color: "#8a988c", marginTop: 4, lineHeight: 1.45 }}>{res?.gate?.why}{held && " — structure clears; the fire is yours."}</div>

            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9.5, color: "#5d6b60", letterSpacing: 1, margin: "12px 0 6px" }}>
              <span>rigor floor {minRigor}/3</span><span>field strength · weakest glass holds</span><span>avg {avgRigor.toFixed(1)}</span>
            </div>
            <div style={{ display: "flex", gap: 3 }}>
              {[0, 1, 2].map((i) => <div key={i} style={{ flex: 1, height: 6, borderRadius: 3, background: i < minRigor ? rigorColor(minRigor) : "#1b241d" }} />)}
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9.5, color: "#5d6b60", letterSpacing: 1, margin: "12px 0 6px" }}>
              <span>structure {grant}</span><span>polarization</span><span>claim {claim}</span>
            </div>
            <div style={{ display: "flex", gap: 4 }}>
              {[0, 1, 2].map((i) => <div key={i} style={{ flex: 1, height: 5, borderRadius: 3, background: i < spread ? (spread >= 2 ? "#f87171" : "#fbbf24") : "#1b241d" }} />)}
            </div>
            {res?.structure?.note && <div style={{ fontSize: 10, color: unverified ? "#f8a071" : "#6f7e72", marginTop: 8 }}>{unverified ? "⚑ UNVERIFIED · " : ""}{res.structure.note}</div>}
          </div>
        )}

        {res?.fallacies?.length > 0 && (
          <div style={{ marginTop: 12, border: "1px solid #3a2420", borderRadius: 12, background: "#120d0c", padding: "11px 14px" }}>
            <div style={{ fontSize: 10, letterSpacing: 2, color: "#b06a52", marginBottom: 7 }}>⚑ FALLACY REPORT</div>
            {res.fallacies.map((f, i) => (
              <div key={i} style={{ marginBottom: 6 }}>
                <span style={{ fontSize: 12, color: "#f0b5a3", fontWeight: 600 }}>{f.name}</span>
                <span style={{ fontSize: 9.5, color: f.severity === "high" ? "#f87171" : f.severity === "med" ? "#fbbf24" : "#8a988c", marginLeft: 6 }}>{f.severity}</span>
                <div style={{ fontSize: 10.5, color: "#9a8d88", lineHeight: 1.4 }}>{f.locus}</div>
              </div>
            ))}
          </div>
        )}
        {res && res.fallacies?.length === 0 && (
          <div style={{ marginTop: 12, fontSize: 10.5, color: "#5d6b60" }}>⌀ no fallacy detected by the active glasses</div>
        )}

        {/* agent reads with rigor-modulated strength */}
        {res?.agents && (
          <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 9 }}>
            {AGENTS.filter((a) => res.agents[a.id]).map((a) => {
              const node = res.agents[a.id]; if (!node) return null;
              const r = node.rigor ?? 0;
              const isFloor = r === minRigor && rigors.length > 1;
              return (
                <div key={a.id} style={{
                  border: `1px solid ${isFloor ? rigorColor(r) + "55" : "#18211b"}`,
                  borderLeft: `3px solid ${a.color}`, borderRadius: 10,
                  background: "#0c100e", padding: "11px 13px",
                  opacity: r === 0 ? 0.7 : 1,
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                    <span style={{ color: a.color, fontSize: 13 }}>{a.glyph}</span>
                    <span style={{ fontFamily: "'Fraunces',serif", fontSize: 14, color: "#e6ede7" }}>{a.name}</span>
                    <span style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 5 }}>
                      <span style={{ display: "flex", gap: 2 }}>
                        {[0,1,2].map(i => <span key={i} style={{ width: 4, height: 9, borderRadius: 1, background: i < r ? rigorColor(r) : "#1b241d" }} />)}
                      </span>
                      <span style={{ fontSize: 9, color: rigorColor(r), letterSpacing: 0.5 }}>{rigorLabel(r)}</span>
                      {isFloor && <span style={{ fontSize: 8, color: rigorColor(r), border: `1px solid ${rigorColor(r)}55`, padding: "1px 5px", borderRadius: 3 }}>FLOOR</span>}
                    </span>
                  </div>
                  <p style={{ margin: 0, fontSize: 12.5, lineHeight: 1.5, color: r >= 2 ? "#dee6df" : "#9aa89c", ...strength(r) }}>{node.read}</p>
                  {node.evidence && <div style={{ fontSize: 9.5, color: "#5d6b60", marginTop: 6, fontFamily: "'JetBrains Mono',monospace" }}>· {node.evidence}</div>}
                </div>
              );
            })}
          </div>
        )}

        {!res && raw && <pre style={{ marginTop: 14, whiteSpace: "pre-wrap", fontSize: 11, color: "#9aa89c", background: "#0c100e", border: "1px solid #18211b", borderRadius: 10, padding: 12 }}>{raw}</pre>}

        <p style={{ fontSize: 9.5, color: "#4a564d", lineHeight: 1.55, marginTop: 18, fontStyle: "italic", fontFamily: "'Fraunces',serif" }}>
          rigor is self-scored — directional, not certified. the weakest glass holds the field because the
          chain is no stronger than its softest link. a confident read with rigor 0 reads visibly quieter than
          a hedged read with rigor 3. that's the point: volume earned, not asserted.
        </p>
      </div>
    </div>
  );
}
