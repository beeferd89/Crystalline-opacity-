import { useState, useEffect, useRef, useMemo } from "react";

// ── Guardian · Crystal Composer ──────────────────────────────────────────────
// Compose an agent by seeding a crystal with facets (character / operations /
// constraints). Three bounded stages gate the composition:
//   BALLAST — a constitutional resting potential derived from the selected
//             facets, weighted toward constraint anchors. Set at compile.
//   HELIOS  — a debounced orienting sweep. It only runs inside the Van Allen
//             passband; it orients the field, it never authorizes it.
//   GUARDIAN— a running A/B-wave read of the dispersed field against ballast,
//             reporting STABLE or DRIFT against a ballast-scaled threshold.
// Nothing here calls a model or a network; it is a local instrument.

const MONO = "'JetBrains Mono', ui-monospace, monospace";

// ── Physics constants ────────────────────────────────────────────────────────
const TAU = Math.PI * 2;
const PHI = (1 + Math.sqrt(5)) / 2;
const MOSFET_THRESHOLD  = 0.62;   // below this: subthreshold silence
const PASSBAND_UPPER    = 1.18;   // above this: over-determined, deflect
const DECAY_RATES = { c: 0.92, o: 0.78, x: 0.97 }; // photochemical decay per type

// ── Facet library ────────────────────────────────────────────────────────────
const FACETS = {
  character: [
    { id:"c1", label:"Direct",     glyph:"◈", color:"#7DF9C8", weight:0.90 },
    { id:"c2", label:"Curious",    glyph:"◇", color:"#A78BFA", weight:0.70 },
    { id:"c3", label:"Analytical", glyph:"⬡", color:"#60A5FA", weight:0.85 },
    { id:"c4", label:"Nurturing",  glyph:"◉", color:"#F472B6", weight:0.60 },
    { id:"c5", label:"Precise",    glyph:"▣", color:"#FBBF24", weight:0.95 },
    { id:"c6", label:"Adaptive",   glyph:"⬟", color:"#34D399", weight:0.75 },
  ],
  operations: [
    { id:"o1", label:"Summarize",  glyph:"⊕", color:"#93C5FD", weight:0.80 },
    { id:"o2", label:"Research",   glyph:"⊗", color:"#C4B5FD", weight:0.90 },
    { id:"o3", label:"Draft",      glyph:"⊞", color:"#6EE7B7", weight:0.70 },
    { id:"o4", label:"Monitor",    glyph:"⊡", color:"#FCA5A5", weight:0.85 },
    { id:"o5", label:"Schedule",   glyph:"⊟", color:"#FDE68A", weight:0.75 },
    { id:"o6", label:"Synthesize", glyph:"⊛", color:"#A5F3FC", weight:0.95 },
  ],
  constraints: [
    { id:"x1", label:"No Speculation", glyph:"⛶", color:"#FB923C", weight:1.00 },
    { id:"x2", label:"Cite Sources",   glyph:"⛿", color:"#A3E635", weight:0.90 },
    { id:"x3", label:"Stay Scoped",    glyph:"⛻", color:"#E879F9", weight:0.85 },
    { id:"x4", label:"Human Loop",     glyph:"⛼", color:"#38BDF8", weight:0.80 },
  ],
};
// flatten
const ALL_FACETS = [...FACETS.character, ...FACETS.operations, ...FACETS.constraints];

// ── Ballast computation ──────────────────────────────────────────────────────
function computeBallast(selected) {
  if (!selected.length) return 1.0;
  const constraints = selected.filter(f => f.id[0] === "x");
  const total = selected.reduce((a, f) => a + f.weight, 0) / selected.length;
  const constW = constraints.length
    ? constraints.reduce((a, f) => a + f.weight, 0) / constraints.length
    : 0;
  // Ballast = weighted blend of overall mean and constraint anchor
  const blend = 0.4 * total + 0.6 * (constW || total);
  return parseFloat(blend.toFixed(3));
}

// ── Combined field weight ────────────────────────────────────────────────────
function fieldWeight(selected) {
  if (!selected.length) return 0;
  return selected.reduce((a, f) => a + f.weight, 0) / selected.length;
}

// ── Van Allen zone ───────────────────────────────────────────────────────────
function vanAllenZone(fw) {
  if (fw < MOSFET_THRESHOLD) return "sub";
  if (fw > PASSBAND_UPPER)   return "over";
  return "pass";
}

// ── Helios hook (debounce + A/B wave + Van Allen gate) ───────────────────────
function useHelios(selected) {
  const fw = fieldWeight(selected);
  const zone = vanAllenZone(fw);
  const delay = useMemo(() => {
    // Quasicrystalline cadence: scales with PHI relative to facet count
    const n = Math.max(selected.length, 1);
    return 600 + (n * PHI * 80);
  }, [selected.length]);

  const [progress, setProgress]   = useState(0);
  const [ready, setReady]         = useState(false);
  const [dispersed, setDispersed] = useState([]);
  const [aWave, setAWave]         = useState(null); // sharp negative onset
  const [bWave, setBWave]         = useState(null); // slow positive emission
  const animRef = useRef(null);

  const key = selected.map(f=>f.id).sort().join(",");

  useEffect(() => {
    setReady(false);
    setProgress(0);
    setAWave(null);
    setBWave(null);
    cancelAnimationFrame(animRef.current);

    if (!selected.length || zone !== "pass") {
      setDispersed([]);
      return;
    }

    // A-wave fires immediately — sharp photoreceptor hit
    setAWave(-(fw * 0.4));

    const start = performance.now();
    const tick = now => {
      const t = Math.min((now - start) / delay, 1);
      setProgress(t);
      if (t < 1) {
        animRef.current = requestAnimationFrame(tick);
      } else {
        // B-wave: slow positive recovery after Helios completes
        const scattered = selected.map(f => ({
          ...f,
          weight: Math.max(0, f.weight + (Math.random() - 0.5) * 0.07),
        }));
        setBWave(+(fw * 0.6));
        setReady(true);
        setDispersed(scattered);
      }
    };
    animRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(animRef.current);
  }, [key, zone]);

  return { progress, ready, dispersed, aWave, bWave, zone, fw, delay };
}

// ── Photochemical decay buffer ───────────────────────────────────────────────
function useDecayBuffer(dispersed, selected) {
  const ghostRef = useRef({}); // facet id → { weight, decay }

  useEffect(() => {
    // On selection change: seed ghosts for removed facets
    const activeIds = new Set(dispersed.map(f => f.id));
    ALL_FACETS.forEach(f => {
      if (!activeIds.has(f.id) && ghostRef.current[f.id]) {
        // already decaying — leave it
      } else if (!activeIds.has(f.id)) {
        delete ghostRef.current[f.id];
      } else {
        ghostRef.current[f.id] = { weight: f.weight, decay: DECAY_RATES[f.id[0]] || 0.88 };
      }
    });
  }, [dispersed]);

  const getDecayedField = () => {
    let total = 0, count = 0;
    Object.values(ghostRef.current).forEach(({ weight }) => {
      total += weight; count++;
    });
    return count ? total / count : 1.0;
  };

  const stepDecay = () => {
    const activeIds = new Set(dispersed.map(f => f.id));
    Object.keys(ghostRef.current).forEach(id => {
      if (!activeIds.has(id)) {
        ghostRef.current[id].weight *= ghostRef.current[id].decay;
        if (ghostRef.current[id].weight < 0.02) delete ghostRef.current[id];
      }
    });
  };

  return { getDecayedField, stepDecay, ghost: ghostRef };
}

// ── Guardian engine ──────────────────────────────────────────────────────────
function useGuardian(dispersed, selected, ballast) {
  const [signal, setSignal] = useState(ballast);
  const [aTrace, setATrace] = useState([]);  // A-wave trace
  const [bTrace, setBTrace] = useState([]);  // B-wave trace
  const bufRef = useRef([]);
  const { getDecayedField, stepDecay } = useDecayBuffer(dispersed, selected);

  useEffect(() => {
    const id = setInterval(() => {
      stepDecay();
      const decayed = getDecayedField();
      const base = dispersed.length
        ? dispersed.reduce((a,f) => a+f.weight,0) / dispersed.length
        : decayed;

      // A-wave: raw photoreceptor hit — noisy, fast
      const aRaw = parseFloat((base - 0.35 + (Math.random()-0.5)*0.18).toFixed(3));
      // B-wave: inner layer integration — slower, positive
      const bRaw = parseFloat((base + 0.28 + (Math.random()-0.5)*0.08).toFixed(3));

      bufRef.current.push(base + (Math.random()-0.5)*0.10);
      if (bufRef.current.length > 12) bufRef.current.shift();
      const avg = parseFloat(
        (bufRef.current.reduce((a,b)=>a+b,0)/bufRef.current.length).toFixed(3)
      );

      setSignal(avg);
      setATrace(p => [aRaw, ...p.slice(0,5)]);
      setBTrace(p => [bRaw, ...p.slice(0,5)]);
    }, 1100);
    return () => clearInterval(id);
  }, [dispersed, ballast]);

  const dynamicThreshold = Math.max(0.20, 0.38 - (ballast - 0.6) * 0.4);
  const stable = Math.abs(signal - ballast) < dynamicThreshold;

  return { signal, aTrace, bTrace, stable, dynamicThreshold };
}

// ── Torus geometry ───────────────────────────────────────────────────────────
function tPt(theta, phi, R=68, r=24) {
  const x = (R + r*Math.cos(phi)) * Math.cos(theta);
  const y = (R + r*Math.cos(phi)) * Math.sin(theta);
  const z = r * Math.sin(phi);
  const tilt = 0.44;
  return { sx:x, sy: y*Math.cos(tilt)-z*Math.sin(tilt), depth: y*Math.sin(tilt)+z*Math.cos(tilt) };
}

// ── Canvas ───────────────────────────────────────────────────────────────────
function CrystalCanvas({ selected, progress, ready, zone, fw, tick, ballast }) {
  const W=310, H=310, cx=W/2, cy=H/2;

  // Torus wireframe
  const wires = [];
  for (let i=0;i<28;i++) {
    const t1=(i/28)*TAU, t2=((i+1)/28)*TAU;
    for (let j=0;j<8;j++) {
      const ph=(j/8)*TAU;
      const a=tPt(t1,ph), b=tPt(t2,ph);
      wires.push({x1:cx+a.sx,y1:cy+a.sy,x2:cx+b.sx,y2:cy+b.sy,d:a.depth});
    }
  }

  // Helios ring geometry
  const hR = 90;
  const zoneColor = zone==="pass"?"#FBBF24":zone==="over"?"#FB923C":"#334155";
  const arcEnd = progress * TAU;
  const ax = cx + Math.cos(-Math.PI/2+arcEnd)*hR;
  const ay = cy + Math.sin(-Math.PI/2+arcEnd)*hR;
  const lg = arcEnd > Math.PI ? 1:0;

  // Nodes — superposition clouds before ready, definite after
  const nodes = selected.map((f,i) => {
    const theta = (i/Math.max(selected.length,1))*TAU + tick*0.004;
    const phi   = (i*PHI) % TAU;
    const p = tPt(theta, phi);
    return { f, x:cx+p.sx, y:cy+p.sy, depth:p.depth };
  }).sort((a,b)=>a.depth-b.depth);

  return (
    <svg width={W} height={H} style={{overflow:"visible"}}>
      {/* Depth rings */}
      {[25,52,90,128].map((r,i)=>(
        <circle key={i} cx={cx} cy={cy} r={r}
          fill="none" stroke="rgba(125,249,200,0.03)" strokeWidth={1}/>
      ))}

      {/* Torus wireframe */}
      {wires.map((l,i)=>(
        <line key={i} x1={l.x1} y1={l.y1} x2={l.x2} y2={l.y2}
          stroke={`rgba(96,165,250,${0.025+Math.max(0,l.d/120)*0.06})`}
          strokeWidth={0.5}/>
      ))}

      {/* Ballast ground ring — constitutional, fixed */}
      <circle cx={cx} cy={cy} r={hR * ballast * 0.72}
        fill="none"
        stroke="rgba(125,249,200,0.12)"
        strokeWidth={1}
        strokeDasharray="1 5"
      />

      {/* Subthreshold silence indicator */}
      {zone==="sub" && selected.length>0 && (
        <text x={cx} y={cy-110} textAnchor="middle"
          fill="rgba(51,65,85,0.8)" fontSize={9}
          fontFamily={MONO} letterSpacing={3}>
          SUBTHRESHOLD · SILENT
        </text>
      )}
      {zone==="over" && (
        <text x={cx} y={cy-110} textAnchor="middle"
          fill="rgba(251,146,60,0.7)" fontSize={9}
          fontFamily={MONO} letterSpacing={3}>
          OVER-DETERMINED · DEFLECT
        </text>
      )}

      {/* Van Allen passband band */}
      {zone==="pass" && (
        <>
          <circle cx={cx} cy={cy} r={hR*0.88} fill="none"
            stroke="rgba(251,191,36,0.04)" strokeWidth={10}/>
          <circle cx={cx} cy={cy} r={hR*1.08} fill="none"
            stroke="rgba(251,191,36,0.02)" strokeWidth={6}/>
        </>
      )}

      {/* Mycelium */}
      <g opacity={ready?0.35:0.12}>
        {nodes.map(({f,x,y},ti)=>
          [0,0.6,-0.6].map((_,bi)=>{
            const a=(ti/Math.max(nodes.length,1))*TAU+tick*0.003+bi*0.5;
            const len=14+bi*4;
            return <line key={`m${ti}${bi}`}
              x1={x} y1={y}
              x2={x+Math.cos(a)*len} y2={y+Math.sin(a)*len}
              stroke={f.color} strokeWidth={0.55} strokeLinecap="round"/>;
          })
        )}
      </g>

      {/* Bonds */}
      {nodes.map((n,i)=>nodes.slice(i+1).map((m,j)=>{
        const d=Math.hypot(n.x-m.x,n.y-m.y);
        if(d>108)return null;
        return <line key={`b${i}${j}`} x1={n.x} y1={n.y} x2={m.x} y2={m.y}
          stroke={`${n.f.color}18`} strokeWidth={0.6}/>;
      }))}

      {/* Helios ring */}
      {selected.length>0 && zone==="pass" && (
        <>
          <circle cx={cx} cy={cy} r={hR}
            fill="none" stroke={`${zoneColor}10`} strokeWidth={1} strokeDasharray="2 8"/>
          {progress>0 && !ready && (
            <path d={`M ${cx} ${cy-hR} A ${hR} ${hR} 0 ${lg} 1 ${ax} ${ay}`}
              fill="none" stroke={zoneColor} strokeWidth={1.5}
              strokeLinecap="round" opacity={0.7}/>
          )}
          {ready && (
            <circle cx={cx} cy={cy} r={hR}
              fill="none" stroke={`${zoneColor}60`} strokeWidth={1.5}/>
          )}
        </>
      )}
      {zone==="over" && selected.length>0 && (
        <circle cx={cx} cy={cy} r={hR}
          fill="none" stroke="#FB923C50" strokeWidth={1.5} strokeDasharray="4 4"/>
      )}

      {/* Facet nodes — superposition cloud before ready */}
      {nodes.map(({f,x,y,depth})=>{
        const sc=0.80+(depth/120)*0.34;
        const r=15*sc;
        if (!ready) {
          // Superposition: render as probability cloud
          return (
            <g key={f.id}>
              {[0,1,2].map(qi=>{
                const qa=(qi/3)*TAU + tick*0.008*((qi%2)?1:-1);
                const qr=r*(0.6+qi*0.35);
                return <circle key={qi}
                  cx={x+Math.cos(qa)*3} cy={y+Math.sin(qa)*3} r={qr}
                  fill="none" stroke={`${f.color}${qi===0?"40":"20"}`}
                  strokeWidth={0.7}/>;
              })}
              <text x={x} y={y} textAnchor="middle" dominantBaseline="central"
                fontSize={11*sc} fill={`${f.color}60`} style={{userSelect:"none"}}>
                {f.glyph}
              </text>
            </g>
          );
        }
        // Collapsed — definite
        return (
          <g key={f.id} transform={`translate(${x},${y})`}>
            {Array.from({length:5}).map((_,fi)=>{
              const a1=(fi/5)*TAU, a2=((fi+1)/5)*TAU, rx=r*0.66;
              return <polygon key={fi}
                points={`0,0 ${Math.cos(a1)*rx},${Math.sin(a1)*rx} ${Math.cos(a2)*rx},${Math.sin(a2)*rx}`}
                fill={`${f.color}10`} stroke={`${f.color}28`} strokeWidth={0.4}/>;
            })}
            <circle r={r} fill={`${f.color}14`} stroke={`${f.color}55`} strokeWidth={0.9}/>
            <text textAnchor="middle" dominantBaseline="central"
              fontSize={12*sc} fill={f.color} style={{userSelect:"none"}}>
              {f.glyph}
            </text>
          </g>
        );
      })}

      {/* Guardian core */}
      <circle cx={cx} cy={cy} r={ready?8:3}
        fill={ready?"#7DF9C828":"#7DF9C806"}
        stroke={ready?"#7DF9C8":"#7DF9C830"}
        strokeWidth={1} style={{transition:"all 0.8s ease"}}/>
      <circle cx={cx} cy={cy} r={1.8} fill="#7DF9C8" opacity={0.9}/>

      {/* Phase label */}
      <text x={cx} y={cy+148} textAnchor="middle"
        fill={
          !selected.length?"rgba(255,255,255,0.08)":
          ready?"rgba(125,249,200,0.45)":
          zone==="pass"?"rgba(251,191,36,0.38)":
          zone==="over"?"rgba(251,146,60,0.5)":
          "rgba(255,255,255,0.08)"
        }
        fontSize={9} fontFamily={MONO} letterSpacing={3}>
        {!selected.length?"SEED THE CRYSTAL":
         ready?"CRYSTAL COLLAPSED · DEFINITE":
         zone==="pass"?"SUPERPOSITION · HELIOS SWEEPING":
         zone==="over"?"FIELD OVER-DETERMINED":
         "BELOW GATE THRESHOLD"}
      </text>
    </svg>
  );
}

// ── Ballast panel ────────────────────────────────────────────────────────────
function BallastPanel({ ballast, selected, dynamicThreshold }) {
  const constraints = selected.filter(f=>f.id[0]==="x");
  const bar = Math.min(ballast / 1.1, 1);
  return (
    <div style={{
      fontFamily:MONO,fontSize:11,
      background:"rgba(0,0,0,0.6)",
      border:"1px solid rgba(125,249,200,0.15)",
      borderRadius:8,padding:"13px 15px",
    }}>
      <div style={{letterSpacing:3,fontSize:9,color:"rgba(255,255,255,0.18)",marginBottom:9}}>
        BALLAST · CONSTITUTIONAL
      </div>
      {/* Ballast bar */}
      <div style={{height:3,background:"rgba(255,255,255,0.05)",borderRadius:2,marginBottom:8}}>
        <div style={{
          height:"100%",width:`${bar*100}%`,
          background:`linear-gradient(90deg,#7DF9C8,#60A5FA)`,
          borderRadius:2,transition:"width 0.5s ease",
        }}/>
      </div>
      <div style={{color:"#7DF9C8",letterSpacing:1,marginBottom:6}}>
        ψ = <span style={{fontSize:13}}>{ballast.toFixed(3)}</span>
      </div>
      <div style={{color:"rgba(255,255,255,0.25)",fontSize:10,lineHeight:1.8}}>
        threshold: <span style={{color:"rgba(125,249,200,0.5)"}}>{dynamicThreshold.toFixed(3)}</span><br/>
        anchors: <span style={{color:"#FB923C"}}>{constraints.length} constraint{constraints.length!==1?"s":""}</span>
      </div>
      <div style={{
        marginTop:9,fontSize:9,color:"rgba(255,255,255,0.12)",
        lineHeight:1.9,letterSpacing:1,
        borderTop:"1px solid rgba(255,255,255,0.05)",paddingTop:7,
      }}>
        resting membrane potential<br/>
        set at compile · immutable at runtime<br/>
        higher ballast → more drift resistance
      </div>
    </div>
  );
}

// ── Helios panel ─────────────────────────────────────────────────────────────
function HeliosPanel({ progress, ready, zone, fw, delay }) {
  const zoneLabel = zone==="pass"?"PASSBAND":zone==="over"?"DEFLECTING":"SUBTHRESHOLD";
  const zoneColor = zone==="pass"?"#FBBF24":zone==="over"?"#FB923C":"#334155";
  return (
    <div style={{
      fontFamily:MONO,fontSize:11,
      background:"rgba(0,0,0,0.6)",
      border:`1px solid ${zone==="pass"?"rgba(251,191,36,0.22)":"rgba(255,255,255,0.06)"}`,
      borderRadius:8,padding:"13px 15px",
    }}>
      <div style={{letterSpacing:3,fontSize:9,color:"rgba(255,255,255,0.18)",marginBottom:9}}>
        HELIOS · INVARIANT
      </div>
      <div style={{
        display:"flex",alignItems:"center",gap:8,marginBottom:8,
      }}>
        <div style={{
          fontSize:9,letterSpacing:2,padding:"2px 7px",borderRadius:3,
          background:`${zoneColor}20`,color:zoneColor,border:`1px solid ${zoneColor}40`,
        }}>{zoneLabel}</div>
        <div style={{fontSize:10,color:"rgba(255,255,255,0.25)"}}>
          fw: {fw.toFixed(3)}
        </div>
      </div>
      <div style={{height:2,background:"rgba(255,255,255,0.05)",borderRadius:2,marginBottom:8}}>
        <div style={{
          height:"100%",width:`${progress*100}%`,
          background:ready?"#FBBF24":`${zoneColor}80`,
          transition:"width 0.08s linear",borderRadius:2,
        }}/>
      </div>
      <div style={{color:ready?zoneColor:`${zoneColor}60`,letterSpacing:1}}>
        {ready?"◉ ring closed":zone==="pass"?`orienting ${Math.round(progress*100)}%`:"◌ gated"}
      </div>
      <div style={{
        marginTop:8,fontSize:9,color:"rgba(255,255,255,0.12)",
        lineHeight:1.9,letterSpacing:1,
      }}>
        cadence: {Math.round(delay)}ms<br/>
        debounce · scatter · Van Allen<br/>
        orients · never authorizes
      </div>
    </div>
  );
}

// ── Guardian panel ────────────────────────────────────────────────────────────
function GuardianPanel({ signal, aTrace, bTrace, stable, ready, ballast, dynamicThreshold }) {
  return (
    <div style={{
      fontFamily:MONO,fontSize:11,
      background:"rgba(0,0,0,0.6)",
      border:`1px solid ${stable?"rgba(125,249,200,0.18)":"rgba(252,165,165,0.22)"}`,
      borderRadius:8,padding:"13px 15px",
    }}>
      <div style={{letterSpacing:3,fontSize:9,color:"rgba(255,255,255,0.18)",marginBottom:9}}>
        GUARDIAN ENGINE
      </div>
      {!ready?(
        <div style={{color:"rgba(251,191,36,0.35)",letterSpacing:1}}>◌ awaiting helios</div>
      ):(
        <>
          <div style={{fontSize:13,color:stable?"#7DF9C8":"#FCA5A5",letterSpacing:1,marginBottom:7}}>
            {stable?"◉ STABLE":"⚠ DRIFT"}
          </div>
          <div style={{color:"rgba(255,255,255,0.2)",marginBottom:2,fontSize:10}}>
            signal: <span style={{color:stable?"#7DF9C8":"#FCA5A5",fontSize:12}}>{signal.toFixed(3)}</span>
            {"  "}ψ: <span style={{color:"rgba(125,249,200,0.5)"}}>{ballast.toFixed(3)}</span>
          </div>
          <div style={{color:"rgba(255,255,255,0.12)",fontSize:10,marginBottom:9}}>
            Δ: {Math.abs(signal-ballast).toFixed(3)} / {dynamicThreshold.toFixed(3)}
          </div>
          {/* A/B wave traces */}
          <div style={{
            borderTop:"1px solid rgba(255,255,255,0.05)",paddingTop:7,
            display:"grid",gridTemplateColumns:"1fr 1fr",gap:8,
          }}>
            <div>
              <div style={{fontSize:8,letterSpacing:2,color:"rgba(96,165,250,0.5)",marginBottom:4}}>
                A-WAVE
              </div>
              {aTrace.map((v,i)=>(
                <div key={i} style={{
                  color:`rgba(96,165,250,${0.6-i*0.09})`,
                  fontSize:10,lineHeight:1.65,
                }}>↓ {v.toFixed(3)}</div>
              ))}
            </div>
            <div>
              <div style={{fontSize:8,letterSpacing:2,color:"rgba(125,249,200,0.5)",marginBottom:4}}>
                B-WAVE
              </div>
              {bTrace.map((v,i)=>(
                <div key={i} style={{
                  color:`rgba(125,249,200,${0.6-i*0.09})`,
                  fontSize:10,lineHeight:1.65,
                }}>↑ {v.toFixed(3)}</div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// ── Echo panel ────────────────────────────────────────────────────────────────
function EchoPanel({ selected, ready, ballast }) {
  const traits = selected.filter(f=>f.id[0]==="c");
  const ops    = selected.filter(f=>f.id[0]==="o");
  const cons   = selected.filter(f=>f.id[0]==="x");

  const sigil = ready && selected.length>=3
    ? selected.map(f=>f.label.slice(0,3).toUpperCase()).join("-")+" CREST"
    : null;

  if(!selected.length) return (
    <div style={{
      fontFamily:MONO,fontSize:11,
      color:"rgba(255,255,255,0.1)",textAlign:"center",
      padding:"14px 0",letterSpacing:2,
    }}>select facets · seed the crystal</div>
  );

  return (
    <div style={{fontFamily:MONO,fontSize:11,lineHeight:1.9}}>
      {traits.length>0&&<div style={{color:"rgba(255,255,255,0.35)"}}>
        <span style={{color:"#A78BFA"}}>character</span> → {traits.map(f=>f.label).join(", ")}
      </div>}
      {ops.length>0&&<div style={{color:"rgba(255,255,255,0.35)"}}>
        <span style={{color:"#60A5FA"}}>operations</span> → {ops.map(f=>f.label).join(", ")}
      </div>}
      {cons.length>0&&<div style={{color:"rgba(255,255,255,0.35)"}}>
        <span style={{color:"#FB923C"}}>constraints</span> → {cons.map(f=>f.label).join(", ")}
      </div>}
      {sigil&&(
        <div style={{
          marginTop:8,paddingTop:8,
          borderTop:"1px solid rgba(255,255,255,0.06)",
          color:"#FBBF24",letterSpacing:2,fontSize:10,
        }}>
          ◈ {sigil}
        </div>
      )}
      {ready&&selected.length>=3&&(
        <div style={{color:"#7DF9C8",letterSpacing:1,marginTop:4}}>
          ballast ψ={ballast.toFixed(3)} · ready to deploy
        </div>
      )}
    </div>
  );
}

// ── Facet tile ────────────────────────────────────────────────────────────────
function FacetTile({ facet, selected, onToggle }) {
  const active = selected.some(s=>s.id===facet.id);
  return (
    <button onClick={()=>onToggle(facet)} style={{
      display:"flex",alignItems:"center",gap:7,
      padding:"5px 9px",
      background:active?`${facet.color}12`:"rgba(255,255,255,0.015)",
      border:`1px solid ${active?facet.color+"50":"rgba(255,255,255,0.055)"}`,
      borderRadius:5,
      color:active?facet.color:"rgba(255,255,255,0.3)",
      fontFamily:MONO,fontSize:11,
      cursor:"pointer",letterSpacing:1,width:"100%",
      transition:"all 0.15s",
    }}>
      <span style={{fontSize:13}}>{facet.glyph}</span>
      <span>{facet.label}</span>
      {active&&<span style={{marginLeft:"auto",fontSize:9,opacity:0.45}}>◉</span>}
    </button>
  );
}

function FacetSection({ title, facets, selected, onToggle }) {
  return (
    <div style={{marginBottom:15}}>
      <div style={{
        fontSize:8,letterSpacing:4,color:"rgba(255,255,255,0.12)",
        marginBottom:6,textTransform:"uppercase",
        fontFamily:MONO,
      }}>{title}</div>
      <div style={{display:"flex",flexDirection:"column",gap:3}}>
        {facets.map(f=>(
          <FacetTile key={f.id} facet={f} selected={selected} onToggle={onToggle}/>
        ))}
      </div>
    </div>
  );
}

// ── Root ──────────────────────────────────────────────────────────────────────
export default function CrystalComposer() {
  const [selected, setSelected] = useState([]);
  const [tick, setTick]         = useState(0);
  const [compiled, setCompiled] = useState(null);

  const ballast = useMemo(()=>computeBallast(selected),[selected]);
  const { progress, ready, dispersed, zone, fw, delay } = useHelios(selected);
  const { signal, aTrace, bTrace, stable, dynamicThreshold } = useGuardian(dispersed, selected, ballast);

  useEffect(()=>{
    const id=setInterval(()=>setTick(t=>t+1),50);
    return()=>clearInterval(id);
  },[]);

  // A compile is only valid for the crystal that produced it — any change to
  // the facet set or a re-sweep of Helios invalidates the record.
  useEffect(()=>{ setCompiled(null); },[selected, ready]);

  const toggle = f => setSelected(prev=>
    prev.some(s=>s.id===f.id)?prev.filter(s=>s.id!==f.id):[...prev,f]
  );

  const deploy = () => {
    setCompiled({
      sigil: selected.map(f=>f.label.slice(0,3).toUpperCase()).join("-")+" CREST",
      ballast,
      signal,
      threshold: dynamicThreshold,
      at: new Date().toLocaleTimeString(),
    });
  };

  return (
    <div style={{
      minHeight:"100vh",
      background:"#040710",
      display:"flex",alignItems:"center",justifyContent:"center",
      padding:24,
      fontFamily:MONO,
    }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,500;1,9..144,500&family=JetBrains+Mono:wght@400;500;700&display=swap');
      `}</style>

      <div style={{
        display:"grid",
        gridTemplateColumns:"185px 1fr 185px",
        gap:16,maxWidth:780,width:"100%",
        alignItems:"start",
      }}>

        {/* LEFT — Facet Library */}
        <div style={{
          background:"rgba(255,255,255,0.012)",
          border:"1px solid rgba(255,255,255,0.05)",
          borderRadius:12,padding:13,
        }}>
          <div style={{fontSize:8,letterSpacing:4,color:"rgba(255,255,255,0.12)",marginBottom:13}}>
            FACET LIBRARY
          </div>
          <FacetSection title="Character"   facets={FACETS.character}   selected={selected} onToggle={toggle}/>
          <FacetSection title="Operations"  facets={FACETS.operations}  selected={selected} onToggle={toggle}/>
          <FacetSection title="Constraints" facets={FACETS.constraints} selected={selected} onToggle={toggle}/>
        </div>

        {/* CENTER */}
        <div style={{display:"flex",flexDirection:"column",alignItems:"center",gap:14}}>
          <div style={{fontSize:9,letterSpacing:5,color:"rgba(255,255,255,0.09)"}}>
            GUARDIAN · CRYSTAL COMPOSER
          </div>
          <div style={{
            background:"rgba(0,0,0,0.6)",
            border:"1px solid rgba(125,249,200,0.06)",
            borderRadius:16,padding:14,
          }}>
            <CrystalCanvas
              selected={selected}
              progress={progress}
              ready={ready}
              zone={zone}
              fw={fw}
              tick={tick}
              ballast={ballast}
            />
          </div>
          <div style={{
            background:"rgba(255,255,255,0.012)",
            border:"1px solid rgba(255,255,255,0.05)",
            borderRadius:10,padding:"11px 15px",width:"100%",
          }}>
            <EchoPanel selected={selected} ready={ready} ballast={ballast}/>
          </div>
          {ready && selected.length>=3 && (
            <button onClick={deploy} style={{
              padding:"8px 28px",background:"transparent",
              border:"1px solid #7DF9C8",color:"#7DF9C8",
              borderRadius:5,fontFamily:MONO,
              fontSize:11,letterSpacing:3,cursor:"pointer",
              transition:"all 0.2s",
            }}>
              DEPLOY TO GUARDIAN
            </button>
          )}
          {compiled && (
            <div style={{
              width:"100%",background:"rgba(0,0,0,0.6)",
              border:"1px solid rgba(125,249,200,0.22)",
              borderRadius:10,padding:"11px 15px",
              fontFamily:MONO,fontSize:10,lineHeight:1.9,
              color:"rgba(255,255,255,0.3)",
            }}>
              <div style={{letterSpacing:3,fontSize:9,color:"rgba(255,255,255,0.18)",marginBottom:7}}>
                COMPILED · {compiled.at}
              </div>
              <div style={{color:"#FBBF24",letterSpacing:2}}>◈ {compiled.sigil}</div>
              <div>ballast ψ: <span style={{color:"#7DF9C8"}}>{compiled.ballast.toFixed(3)}</span></div>
              <div>signal at compile: <span style={{color:"#7DF9C8"}}>{compiled.signal.toFixed(3)}</span></div>
              <div>threshold: ±{compiled.threshold.toFixed(3)}</div>
              <div style={{color:"rgba(255,255,255,0.18)"}}>helios: closed · read-only</div>
              <div style={{
                marginTop:6,paddingTop:6,fontSize:9,letterSpacing:1,
                borderTop:"1px solid rgba(255,255,255,0.05)",
                color:"rgba(255,255,255,0.12)",
              }}>
                local record only · nothing left this browser
              </div>
            </div>
          )}
        </div>

        {/* RIGHT */}
        <div style={{display:"flex",flexDirection:"column",gap:13}}>
          <BallastPanel ballast={ballast} selected={selected} dynamicThreshold={dynamicThreshold}/>
          <HeliosPanel progress={progress} ready={ready} zone={zone} fw={fw} delay={delay}/>
          <GuardianPanel
            signal={signal} aTrace={aTrace} bTrace={bTrace}
            stable={stable} ready={ready}
            ballast={ballast} dynamicThreshold={dynamicThreshold}
          />
        </div>

      </div>
    </div>
  );
}
