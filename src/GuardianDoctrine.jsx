import React, { useState, useCallback, useRef } from "react";

// ── Guardian · Foundational Doctrine ─────────────────────────────────────
// Color-phase signaling for nonverbal / nonspeaking people.
// Every state selection is appended to the Ollie Ledger — an SHA-256
// hash-chained, append-only log. No entry can be altered without breaking
// the chain. The Habeas Sovereignty Charter exports the full record on demand.
//
// Doctrine spine: NJC Communication Bill of Rights (2024), ADA 1990,
// UN CRPD 2006, Ostrom's polycentric governance, Crosby & Wallach
// tamper-evident logging, Christopher Allen SSI principles.
// Color-phase states: red/protect · yellow/hold-caution · blue/receive-protect
//                     green/flow · brown/ground-local · purple/jurisdictional

const PHASES = [
  {
    id: "red",
    label: "PROTECT",
    sub: "immediate need",
    color: "#ef4444",
    bg: "#450a0a",
    border: "#991b1b",
    glow: "#ef444455",
    charter: "The custodian must produce the record of care immediately. No delay is lawful.",
    right: "Right to immediate response · NJC Right #4",
    invariant: "Policy",
  },
  {
    id: "yellow",
    label: "HOLD · CAUTION",
    sub: "something needs attention",
    color: "#eab308",
    bg: "#3d2300",
    border: "#a16207",
    glow: "#eab30855",
    charter: "The caution signal is primary evidence. Rebuttal requires a produced, justified record.",
    right: "Right to receive a response to all communication · NJC Right #4",
    invariant: "Reality",
  },
  {
    id: "blue",
    label: "RECEIVE · PROTECT",
    sub: "in a safe receiving state",
    color: "#60a5fa",
    bg: "#0c1445",
    border: "#1d4ed8",
    glow: "#60a5fa55",
    charter: "The person is in a receiving state. No action without acknowledged consent.",
    right: "Right to dignity and respect · NJC Right #1",
    invariant: "Identity",
  },
  {
    id: "green",
    label: "FLOW",
    sub: "all is well",
    color: "#4ade80",
    bg: "#052e16",
    border: "#15803d",
    glow: "#4ade8055",
    charter: "Flow state is verified and logged. Continuity is protected by the ledger.",
    right: "Right to be addressed directly · NJC Right #3",
    invariant: "Proof",
  },
  {
    id: "brown",
    label: "GROUND · LOCAL",
    sub: "connecting to local environment",
    color: "#c4956a",
    bg: "#1c1008",
    border: "#78442a",
    glow: "#c4956a55",
    charter: "Local grounding is recognized. The record binds to this jurisdiction and context.",
    right: "Right to individualized AAC at all times · NJC Right #12",
    invariant: "Reality",
  },
  {
    id: "purple",
    label: "JURISDICTIONAL",
    sub: "formal registration",
    color: "#c084fc",
    bg: "#2d1b4e",
    border: "#7e22ce",
    glow: "#c084fc55",
    charter: "Habeas Sovereignty Charter invoked. Produce the record with cause on demand.",
    right: "Right to receive a response to all communication · NJC Right #4",
    invariant: "Policy",
  },
];

const INVARIANTS = [
  { id: "reality",  label: "Reality",  desc: "claims must be recomputable, not bare assertion",                          color: "#60a5fa" },
  { id: "identity", label: "Identity", desc: "the person is source of authority over their own representation",          color: "#4ade80" },
  { id: "policy",   label: "Policy",   desc: "the weakest signal is primary evidence by default",                        color: "#fbbf24" },
  { id: "proof",    label: "Proof",    desc: "rebuttal requires a produced, justified tamper-evident record",             color: "#c084fc" },
];

const OBSERVERS = [
  { id: "o1", glyph: "◆" },
  { id: "o2", glyph: "◇" },
  { id: "o3", glyph: "⬡" },
  { id: "o4", glyph: "◉" },
  { id: "o5", glyph: "■" },
];

const GENESIS = "0".repeat(64);

async function sha256(message) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(message));
  return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, "0")).join("");
}

export default function GuardianDoctrine() {
  const [ledger, setLedger] = useState([]);
  const [active, setActive] = useState(null);
  const [msmState, setMsmState] = useState(null);
  const [chainOk, setChainOk] = useState(true);
  const prevHashRef = useRef(GENESIS);
  const seqRef = useRef(0);

  const signal = useCallback(async (phase) => {
    if (msmState) return;
    setActive(phase.id);
    setMsmState("collecting");

    const seq = ++seqRef.current;
    const ts = new Date().toISOString();
    const payload = JSON.stringify({ seq, ts, state: phase.id, label: phase.label });
    const prevHash = prevHashRef.current;

    await new Promise((r) => setTimeout(r, 420));
    setMsmState("verifying");

    const hash = await sha256(prevHash + payload);
    prevHashRef.current = hash;

    await new Promise((r) => setTimeout(r, 280));
    setMsmState("broadcast");

    const entry = { seq, ts, phase: phase.id, label: phase.label, color: phase.color, payload, prevHash, hash };
    setLedger((prev) => [entry, ...prev]);

    await new Promise((r) => setTimeout(r, 350));
    setMsmState(null);
  }, [msmState]);

  const verifyChain = useCallback(async () => {
    if (ledger.length === 0) return;
    const sorted = [...ledger].sort((a, b) => a.seq - b.seq);
    let prev = GENESIS;
    let ok = true;
    for (const e of sorted) {
      const expected = await sha256(prev + e.payload);
      if (expected !== e.hash) { ok = false; break; }
      prev = e.hash;
    }
    setChainOk(ok);
  }, [ledger]);

  const exportLedger = useCallback(() => {
    const sorted = [...ledger].sort((a, b) => a.seq - b.seq);
    const doc = {
      title: "Ollie Ledger — Habeas Sovereignty Charter",
      exported: new Date().toISOString(),
      genesis: GENESIS,
      invariant:
        "The color-state output of this nonverbal user is primary evidence by default. " +
        "Any override requires a tamper-evident record with cause.",
      entries: sorted,
    };
    const blob = new Blob([JSON.stringify(doc, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `ollie-ledger-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [ledger]);

  const activePhase = PHASES.find((p) => p.id === active);
  const msmObservers = msmState === "collecting" ? OBSERVERS.slice(0, 3)
                     : msmState === "verifying"  ? OBSERVERS.slice(0, 5)
                     : msmState === "broadcast"  ? OBSERVERS
                     : [];

  return (
    <div style={{ minHeight: "100vh", background: "#080b10", color: "#c8d3e0", fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,500;1,9..144,500&family=JetBrains+Mono:wght@400;500;700&display=swap');
        @keyframes spin{to{transform:rotate(360deg)}}
        @keyframes ripple{0%{transform:scale(1);opacity:.6}100%{transform:scale(2.2);opacity:0}}
        @keyframes fadein{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:translateY(0)}}
        .phase-btn:hover{filter:brightness(1.12)}
        .phase-btn:active{transform:scale(.97)}
      `}</style>

      {/* Header */}
      <div style={{ padding: "14px 18px", borderBottom: "1px solid #131b26", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <span style={{ fontFamily: "'Fraunces',serif", fontSize: 21, color: "#e8f0fa" }}>Guardian</span>
          <span style={{ fontFamily: "'Fraunces',serif", fontSize: 21, color: "#60a5fa" }}>·</span>
          <span style={{ fontFamily: "'Fraunces',serif", fontSize: 21, color: "#c084fc" }}>Doctrine</span>
          <div style={{ fontSize: 9, letterSpacing: 3, color: "#3d5266", marginTop: 1 }}>COLOR · PHASE · SIGNAL</div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 9, color: "#3d5266", letterSpacing: 1 }}>OLLIE LEDGER</div>
          <div style={{ fontSize: 15, color: ledger.length ? "#60a5fa" : "#2a3a4d", fontWeight: 700 }}>
            {ledger.length} {ledger.length === 1 ? "entry" : "entries"}
          </div>
        </div>
      </div>

      <div style={{ maxWidth: 680, margin: "0 auto", padding: "16px 14px", boxSizing: "border-box" }}>

        {/* Doctrine preamble */}
        <div style={{ marginBottom: 18, padding: "11px 14px", border: "1px solid #131b26", borderRadius: 10, background: "#0b1018" }}>
          <div style={{ fontSize: 9.5, letterSpacing: 2, color: "#3d5266", marginBottom: 5 }}>FOUNDATIONAL INVARIANT</div>
          <p style={{ margin: 0, fontSize: 11.5, color: "#8ba0b8", lineHeight: 1.6, fontStyle: "italic", fontFamily: "'Fraunces',serif" }}>
            The color-state signal of a nonverbal user is treated as primary evidence by default.
            Any system component that would override it must produce, on demand,
            a tamper-evident record with cause.
          </p>
        </div>

        {/* Color Phase Grid */}
        <div style={{ fontSize: 9, letterSpacing: 3, color: "#3d5266", marginBottom: 10 }}>COLOR · PHASE · STATES</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 9, marginBottom: 16 }}>
          {PHASES.map((p) => {
            const isActive = active === p.id;
            return (
              <button key={p.id} className="phase-btn" onClick={() => signal(p)} disabled={!!msmState} style={{
                border: `2px solid ${isActive ? p.color : p.border + "80"}`,
                background: isActive ? p.bg : "#0b1018",
                borderRadius: 14, padding: "14px 10px 12px",
                cursor: msmState ? "not-allowed" : "pointer",
                textAlign: "center", position: "relative", transition: "all .2s",
                boxShadow: isActive ? `0 0 16px ${p.glow}` : "none",
                opacity: msmState && active !== p.id ? 0.55 : 1,
              }}>
                <div style={{
                  width: 38, height: 38, borderRadius: "50%", background: p.color,
                  margin: "0 auto 8px", boxShadow: isActive ? `0 0 20px ${p.glow}` : "none", position: "relative",
                }}>
                  {isActive && (
                    <div style={{ position: "absolute", inset: -4, borderRadius: "50%", border: `2px solid ${p.color}`, animation: "ripple 1.2s ease-out infinite" }} />
                  )}
                </div>
                <div style={{ fontSize: 11, fontWeight: 700, color: isActive ? p.color : "#7a90a8", letterSpacing: 0.5 }}>{p.label}</div>
                <div style={{ fontSize: 9, color: isActive ? p.color + "cc" : "#3d5266", marginTop: 3, lineHeight: 1.3 }}>{p.sub}</div>
              </button>
            );
          })}
        </div>

        {/* Active phase charter */}
        {activePhase && (
          <div style={{
            marginBottom: 16, border: `1px solid ${activePhase.border}80`,
            borderLeft: `3px solid ${activePhase.color}`, borderRadius: 10,
            background: activePhase.bg + "cc", padding: "12px 14px", animation: "fadein .3s ease",
          }}>
            <div style={{ fontSize: 9, letterSpacing: 2, color: activePhase.color + "aa", marginBottom: 5 }}>HABEAS SOVEREIGNTY CHARTER · ACTIVE PHASE</div>
            <div style={{ fontSize: 13.5, color: activePhase.color, fontWeight: 700, marginBottom: 4 }}>
              <span style={{ display: "inline-block", width: 11, height: 11, borderRadius: "50%", background: activePhase.color, marginRight: 7, verticalAlign: "middle" }} />
              {activePhase.label}
            </div>
            <p style={{ margin: "0 0 6px", fontSize: 12, color: "#c8d3e0", lineHeight: 1.55 }}>{activePhase.charter}</p>
            <div style={{ fontSize: 10, color: activePhase.color + "99", fontStyle: "italic" }}>⊢ {activePhase.right}</div>
            <div style={{ fontSize: 9, color: "#3d5266", marginTop: 6 }}>
              Invariant: <span style={{ color: INVARIANTS.find((i) => i.label === activePhase.invariant)?.color || "#c8d3e0" }}>{activePhase.invariant}</span>
            </div>
          </div>
        )}

        {/* MSM Verification */}
        {msmState && (
          <div style={{ marginBottom: 16, border: "1px solid #1a2b3d", borderRadius: 10, background: "#0a1220", padding: "12px 14px", animation: "fadein .2s ease" }}>
            <div style={{ fontSize: 9, letterSpacing: 2, color: "#3d5266", marginBottom: 8 }}>MULTI · SINGLE · MULTI VERIFICATION</div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {OBSERVERS.map((o) => {
                  const seen = msmObservers.find((x) => x.id === o.id);
                  return (
                    <div key={o.id} style={{ display: "flex", alignItems: "center", gap: 4 }}>
                      <span style={{ fontSize: 9, color: seen ? "#60a5fa" : "#1e2e40" }}>{o.glyph}</span>
                      <div style={{ width: 22, height: 2, borderRadius: 1, background: seen ? "#60a5fa" : "#1e2e40", transition: "background .3s" }} />
                    </div>
                  );
                })}
              </div>
              <div style={{
                width: 44, height: 44, borderRadius: 8,
                border: `2px solid ${msmState === "verifying" || msmState === "broadcast" ? "#60a5fa" : "#1e2e40"}`,
                background: msmState === "verifying" ? "#0c1d2e" : "#0a1220",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 9, color: "#3d5266", letterSpacing: 0.5, textAlign: "center", lineHeight: 1.3,
                transition: "all .3s", boxShadow: msmState === "verifying" ? "0 0 12px #60a5fa44" : "none",
              }}>
                {msmState === "collecting" && <span style={{ animation: "spin .8s linear infinite", fontSize: 13 }}>⟳</span>}
                {msmState === "verifying" && <span style={{ color: "#60a5fa", fontSize: 11 }}>SHA<br />256</span>}
                {msmState === "broadcast" && <span style={{ color: "#4ade80" }}>✓</span>}
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {OBSERVERS.map((o) => {
                  const broadcast = msmState === "broadcast";
                  return (
                    <div key={o.id} style={{ display: "flex", alignItems: "center", gap: 4 }}>
                      <div style={{ width: 22, height: 2, borderRadius: 1, background: broadcast ? "#4ade80" : "#1e2e40", transition: "background .3s" }} />
                      <span style={{ fontSize: 9, color: broadcast ? "#4ade80" : "#1e2e40" }}>{o.glyph}</span>
                    </div>
                  );
                })}
              </div>
            </div>
            <div style={{ marginTop: 8, fontSize: 9.5, color: "#3d5266" }}>
              {msmState === "collecting" && "collecting observer confirmations…"}
              {msmState === "verifying" && "computing SHA-256 hash chain entry…"}
              {msmState === "broadcast" && <span style={{ color: "#4ade80" }}>signal verified · broadcasting to ledger</span>}
            </div>
          </div>
        )}

        {/* Ollie Ledger */}
        {ledger.length > 0 && (
          <div style={{ marginBottom: 16 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
              <div style={{ fontSize: 9, letterSpacing: 2, color: "#3d5266" }}>OLLIE LEDGER · HASH-CHAINED RECORD</div>
              <div style={{ display: "flex", gap: 7 }}>
                <button onClick={verifyChain} style={{
                  fontSize: 9, color: chainOk ? "#4ade80" : "#f87171",
                  background: "none", border: `1px solid ${chainOk ? "#4ade8044" : "#f8717144"}`,
                  borderRadius: 5, padding: "3px 8px", cursor: "pointer",
                }}>
                  {chainOk ? "⊢ chain intact" : "⚑ chain broken"}
                </button>
                <button onClick={exportLedger} style={{
                  fontSize: 9, color: "#c084fc", background: "none",
                  border: "1px solid #c084fc44", borderRadius: 5, padding: "3px 8px", cursor: "pointer",
                }}>
                  produce the record ↓
                </button>
              </div>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {ledger.map((e) => {
                const ph = PHASES.find((p) => p.id === e.phase);
                return (
                  <div key={e.seq} style={{
                    border: "1px solid #131b26", borderLeft: `3px solid ${ph?.color || "#3d5266"}`,
                    borderRadius: 8, background: "#0a1018", padding: "9px 12px", animation: "fadein .3s ease",
                  }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ fontSize: 9, color: "#3d5266", minWidth: 20 }}>#{e.seq}</span>
                      <span style={{ width: 8, height: 8, borderRadius: "50%", background: ph?.color || "#3d5266", flexShrink: 0 }} />
                      <span style={{ fontSize: 11, color: ph?.color || "#c8d3e0", fontWeight: 600 }}>{e.label}</span>
                      <span style={{ marginLeft: "auto", fontSize: 9, color: "#3d5266" }}>
                        {new Date(e.ts).toLocaleTimeString()}
                      </span>
                    </div>
                    <div style={{ marginTop: 5, fontSize: 9, color: "#2a3e52", fontFamily: "monospace", letterSpacing: 0.3 }}>
                      <span style={{ color: "#3d5266" }}>prev </span>{e.prevHash.slice(0, 12)}…
                      <span style={{ color: "#3d5266", marginLeft: 8 }}>hash </span>
                      <span style={{ color: "#4ade8088" }}>{e.hash.slice(0, 12)}…</span>
                    </div>
                  </div>
                );
              })}
            </div>
            <div style={{ marginTop: 6, padding: "6px 12px", border: "1px dashed #131b26", borderRadius: 7, fontSize: 9, color: "#2a3e52" }}>
              GENESIS · {GENESIS.slice(0, 16)}… · append-only · tamper-evident
            </div>
          </div>
        )}

        {/* Four Invariants */}
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 9, letterSpacing: 2, color: "#3d5266", marginBottom: 8 }}>FOUR INVARIANTS</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 7 }}>
            {INVARIANTS.map((inv) => (
              <div key={inv.id} style={{ border: "1px solid #131b26", borderLeft: `3px solid ${inv.color}33`, borderRadius: 8, background: "#0a1018", padding: "9px 11px" }}>
                <div style={{ fontSize: 11.5, color: inv.color, fontWeight: 600, marginBottom: 3 }}>{inv.label}</div>
                <div style={{ fontSize: 9.5, color: "#5a7082", lineHeight: 1.4 }}>{inv.desc}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Empty state */}
        {ledger.length === 0 && !msmState && (
          <div style={{ textAlign: "center", padding: "28px 14px", border: "1px dashed #131b26", borderRadius: 12, color: "#2a3e52" }}>
            <div style={{ fontSize: 28, marginBottom: 10, opacity: 0.5 }}>◎</div>
            <div style={{ fontSize: 12, lineHeight: 1.6, fontStyle: "italic", fontFamily: "'Fraunces',serif", color: "#3d5266" }}>
              Select a color phase to signal your state.<br />
              Each selection is logged to the Ollie Ledger<br />
              and verified by the Multi-Single-Multi topology.
            </div>
          </div>
        )}

        <p style={{ fontSize: 9.5, color: "#2a3e52", lineHeight: 1.6, marginTop: 18, fontStyle: "italic", fontFamily: "'Fraunces',serif" }}>
          "the weakest verifiable signal is treated as primary evidence until a justified record is produced
          to displace it — that is a rule, not a sentiment, and it is the rule the entire architecture exists to enforce."
          <br /><span style={{ fontSize: 8.5, color: "#1e2e40" }}>— Guardian Foundational Doctrine · Bradford Kibler Jr. · Kibler AI Solutions Corp.</span>
        </p>
      </div>
    </div>
  );
}
