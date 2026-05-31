import React, { useState, useEffect, useMemo } from "react";

const API_URL =
  "https://waterservices.usgs.gov/nwis/gwlevels/?format=json&stateCd=oh&siteStatus=all&period=P30D";

const PAGE_SIZE = 25;

function depthColor(ft) {
  if (ft === null) return "#5b6678";
  if (ft < 10) return "#4ade80";
  if (ft < 25) return "#86efac";
  if (ft < 50) return "#fbbf24";
  if (ft < 100) return "#f8a071";
  return "#f87171";
}

function qualBadge(q) {
  if (!q) return null;
  const map = { A: { label: "approved", color: "#4ade80" }, P: { label: "provisional", color: "#fbbf24" }, e: { label: "estimated", color: "#f8a071" } };
  return map[q] || { label: q, color: "#5b6678" };
}

function parseSeries(ts) {
  const si = ts.sourceInfo || {};
  const siteCode = (si.siteCode || [])[0]?.value || "—";
  const siteName = si.siteName || "—";
  const geo = si.geoLocation?.geogLocation || {};
  const lat = geo.latitude ?? null;
  const lon = geo.longitude ?? null;

  const props = si.siteProperty || [];
  const county = props.find((p) => p.name === "countyCd")?.value || null;

  const vals = (ts.values || [])[0]?.value || [];
  const last = vals.length ? vals[vals.length - 1] : null;
  const raw = last ? parseFloat(last.value) : null;
  const depth = raw !== null && raw !== -999999 ? raw : null;
  const dateTime = last?.dateTime || null;
  const qualifier = last?.qualifiers?.[0] || null;

  const unit = ts.variable?.unit?.unitCode || "ft";

  return { siteCode, siteName, lat, lon, county, depth, unit, dateTime, qualifier };
}

function fmt(dateStr) {
  if (!dateStr) return "—";
  const d = new Date(dateStr);
  if (isNaN(d)) return dateStr.slice(0, 10);
  return d.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
}

export default function GroundwaterLevels() {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState({ key: "depth", dir: 1 });
  const [page, setPage] = useState(0);

  useEffect(() => {
    setLoading(true);
    setErr("");
    fetch(API_URL)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((json) => {
        const series = json?.value?.timeSeries || [];
        setData(series.map(parseSeries));
        setLoading(false);
      })
      .catch((e) => {
        setErr("Failed to load USGS data: " + e.message);
        setLoading(false);
      });
  }, []);

  const withReadings = data.filter((d) => d.depth !== null).length;

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const rows = q
      ? data.filter((d) => d.siteName.toLowerCase().includes(q) || d.siteCode.includes(q))
      : data;
    return [...rows].sort((a, b) => {
      const { key, dir } = sort;
      if (key === "depth") {
        const av = a.depth ?? Infinity;
        const bv = b.depth ?? Infinity;
        return (av - bv) * dir;
      }
      if (key === "date") {
        const av = a.dateTime || "";
        const bv = b.dateTime || "";
        return av < bv ? -dir : av > bv ? dir : 0;
      }
      if (key === "name") {
        return a.siteName.localeCompare(b.siteName) * dir;
      }
      return 0;
    });
  }, [data, query, sort]);

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const pageRows = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  const toggleSort = (key) => {
    setSort((s) => s.key === key ? { key, dir: -s.dir } : { key, dir: 1 });
    setPage(0);
  };

  const sortArrow = (key) => sort.key === key ? (sort.dir === 1 ? " ↑" : " ↓") : "";

  const onQuery = (v) => { setQuery(v); setPage(0); };

  const COL = { name: "#cdd6cf", depth: "#4ade80", date: "#7dd3fc", code: "#a78bfa", qual: "#fbbf24" };

  return (
    <div style={{ minHeight: "100vh", background: "#0b0d0c", color: "#cdd6cf", fontFamily: "'JetBrains Mono', ui-monospace, monospace" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,500;1,9..144,500&family=JetBrains+Mono:wght@400;500;700&display=swap');
        @keyframes spin{to{transform:rotate(360deg)}}
        @keyframes pulse{0%,100%{opacity:.4}50%{opacity:1}}
        input::placeholder{color:#3f5043}
        .gw-row:hover{background:#0f1510 !important}
        .gw-btn:hover{opacity:.8}
        .gw-sort:hover{color:#aef0c8;cursor:pointer}
      `}</style>

      {/* header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 16px", borderBottom: "1px solid #18211b" }}>
        <div>
          <span style={{ fontFamily: "'Fraunces',serif", fontSize: 20, color: "#e8efe9" }}>Groundwater</span>
          <span style={{ fontFamily: "'Fraunces',serif", fontSize: 20, color: "#4ade80" }}>Levels</span>
          <span style={{ fontSize: 9, color: "#5d6b60", marginLeft: 8, letterSpacing: 2 }}>OHIO · USGS NWIS</span>
        </div>
        <div style={{ fontSize: 10, color: "#5d6b60", textAlign: "right" }}>
          <div>last 30 days</div>
          {!loading && !err && (
            <div style={{ color: "#4ade80" }}>{withReadings}/{data.length} sites reporting</div>
          )}
        </div>
      </div>

      <div style={{ maxWidth: 900, margin: "0 auto", padding: "14px 16px", boxSizing: "border-box" }}>

        {/* search */}
        <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 14 }}>
          <input
            value={query}
            onChange={(e) => onQuery(e.target.value)}
            placeholder="filter by site name or number…"
            style={{
              flex: 1, background: "#0e1210", color: "#dbe3dd", border: "1px solid #1b241d",
              borderRadius: 9, padding: "8px 12px", fontSize: 12,
              fontFamily: "'JetBrains Mono',monospace", outline: "none",
            }}
          />
          {query && (
            <button onClick={() => onQuery("")} className="gw-btn" style={{
              background: "#0e1210", border: "1px solid #1b241d", color: "#7c8a80",
              borderRadius: 8, padding: "7px 10px", fontSize: 11, cursor: "pointer",
            }}>✕</button>
          )}
          <span style={{ fontSize: 10, color: "#5d6b60", whiteSpace: "nowrap" }}>
            {filtered.length} site{filtered.length !== 1 ? "s" : ""}
          </span>
        </div>

        {/* depth legend */}
        {!loading && !err && data.length > 0 && (
          <div style={{ display: "flex", gap: 12, fontSize: 9, color: "#5d6b60", marginBottom: 12, flexWrap: "wrap" }}>
            {[["< 10 ft", "#4ade80"], ["10–25 ft", "#86efac"], ["25–50 ft", "#fbbf24"], ["50–100 ft", "#f8a071"], ["> 100 ft", "#f87171"]].map(([label, color]) => (
              <span key={label} style={{ display: "flex", alignItems: "center", gap: 4 }}>
                <span style={{ width: 8, height: 8, borderRadius: 2, background: color, display: "inline-block" }} />
                {label}
              </span>
            ))}
            <span style={{ marginLeft: "auto" }}>depth below land surface</span>
          </div>
        )}

        {/* loading */}
        {loading && (
          <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "40px 0", justifyContent: "center", color: "#5d6b60", fontSize: 12 }}>
            <span style={{ width: 14, height: 14, border: "2px solid #1b241d", borderTopColor: "#4ade80", borderRadius: "50%", animation: "spin .8s linear infinite", display: "inline-block" }} />
            fetching Ohio groundwater sites…
          </div>
        )}

        {/* error */}
        {err && (
          <div style={{ color: "#f87171", fontSize: 12, padding: "20px 0", lineHeight: 1.6 }}>
            ⚑ {err}
            <div style={{ fontSize: 10, color: "#5d6b60", marginTop: 6 }}>
              source: waterservices.usgs.gov/nwis/gwlevels · stateCd=oh · period=P30D
            </div>
          </div>
        )}

        {/* table */}
        {!loading && !err && data.length > 0 && (
          <>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11.5 }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid #1b241d" }}>
                    {[
                      ["name", "Site Name", COL.name],
                      ["code", "Site #", COL.code],
                      ["depth", "Depth (ft bls)", COL.depth],
                      ["date", "Date", COL.date],
                      ["qual", "Status", COL.qual],
                    ].map(([key, label, color]) => (
                      <th
                        key={key}
                        className="gw-sort"
                        onClick={() => key !== "qual" && toggleSort(key)}
                        style={{
                          textAlign: "left", padding: "6px 10px 8px",
                          fontSize: 9, letterSpacing: 1.5, color,
                          userSelect: "none", cursor: key !== "qual" ? "pointer" : "default",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {label}{key !== "qual" ? sortArrow(key) : ""}
                      </th>
                    ))}
                    <th style={{ padding: "6px 10px 8px", fontSize: 9, letterSpacing: 1.5, color: "#5d6b60", whiteSpace: "nowrap" }}>
                      COORDS
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {pageRows.map((row, i) => {
                    const dc = depthColor(row.depth);
                    const qb = qualBadge(row.qualifier);
                    return (
                      <tr
                        key={row.siteCode + i}
                        className="gw-row"
                        style={{
                          borderBottom: "1px solid #111a13",
                          background: i % 2 === 0 ? "#0c100e" : "#0b0e0c",
                          transition: "background .1s",
                        }}
                      >
                        <td style={{ padding: "8px 10px", color: "#d0d8d2", maxWidth: 280, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {row.siteName}
                        </td>
                        <td style={{ padding: "8px 10px", color: "#a78bfa", fontFamily: "'JetBrains Mono',monospace", whiteSpace: "nowrap" }}>
                          {row.siteCode}
                        </td>
                        <td style={{ padding: "8px 10px", whiteSpace: "nowrap" }}>
                          {row.depth !== null ? (
                            <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                              <span style={{ width: 6, height: 6, borderRadius: 1, background: dc, display: "inline-block", flexShrink: 0 }} />
                              <span style={{ color: dc, fontWeight: 600 }}>{row.depth.toFixed(2)}</span>
                              <span style={{ color: "#5d6b60", fontSize: 9 }}>{row.unit}</span>
                            </span>
                          ) : (
                            <span style={{ color: "#3f5043", fontStyle: "italic" }}>no data</span>
                          )}
                        </td>
                        <td style={{ padding: "8px 10px", color: "#7dd3fc", whiteSpace: "nowrap", fontSize: 11 }}>
                          {fmt(row.dateTime)}
                        </td>
                        <td style={{ padding: "8px 10px" }}>
                          {qb ? (
                            <span style={{
                              fontSize: 8.5, color: qb.color, border: `1px solid ${qb.color}44`,
                              borderRadius: 3, padding: "1px 5px", letterSpacing: 0.5,
                            }}>
                              {qb.label}
                            </span>
                          ) : <span style={{ color: "#3f5043" }}>—</span>}
                        </td>
                        <td style={{ padding: "8px 10px", color: "#5d6b60", fontSize: 10, whiteSpace: "nowrap" }}>
                          {row.lat !== null ? `${row.lat.toFixed(3)}, ${row.lon.toFixed(3)}` : "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* pagination */}
            {totalPages > 1 && (
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 14, fontSize: 11 }}>
                <button
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  disabled={page === 0}
                  className="gw-btn"
                  style={{
                    background: "#0e1210", border: "1px solid #1b241d", color: page === 0 ? "#3f5043" : "#aef0c8",
                    borderRadius: 7, padding: "6px 12px", fontSize: 11, cursor: page === 0 ? "default" : "pointer",
                  }}
                >← prev</button>
                <span style={{ color: "#5d6b60" }}>
                  page {page + 1} / {totalPages} · {filtered.length} sites
                </span>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                  disabled={page >= totalPages - 1}
                  className="gw-btn"
                  style={{
                    background: "#0e1210", border: "1px solid #1b241d",
                    color: page >= totalPages - 1 ? "#3f5043" : "#aef0c8",
                    borderRadius: 7, padding: "6px 12px", fontSize: 11,
                    cursor: page >= totalPages - 1 ? "default" : "pointer",
                  }}
                >next →</button>
              </div>
            )}

            <p style={{ fontSize: 9.5, color: "#4a564d", lineHeight: 1.55, marginTop: 18, fontStyle: "italic", fontFamily: "'Fraunces',serif" }}>
              data from USGS National Water Information System · Ohio groundwater monitoring network ·
              depth values in feet below land surface (ft bls) · "approved" = reviewed for publication,
              "provisional" = subject to revision · query covers the last 30 days of discrete field measurements.
            </p>
          </>
        )}
      </div>
    </div>
  );
}
