// Variables used by Scriptable.
// icon-color: deep-purple; icon-glyph: compass;
//
// moon_compass_widget.js - the compass leg, on your Home/Lock Screen.
//
// A Scriptable (iOS) widget port of moon_lines.py. Same physics, same
// GO/HOLD/STOP gates, same "audit before trusting" spirit - translated to
// JavaScript only because Scriptable widgets run JS on-device, not Python.
// `Location.current()` supplies latitude/longitude/altitude (the same fix the
// "What is my Elevation" widget already pulls); everything past that is pure
// geometry. No network, nothing invented, nothing tuned.
//
// THREE LENSES, ONE READOUT:
//   COMPASS  (geometry)    - is the Moon's bearing usable right now?
//                            STOP below the horizon, HOLD within HORIZON_BAND
//                            (parallax + refraction blur the fix ~1 deg there).
//   LIGHT    (luminescent) - is there enough moonlight to drive a light-keyed
//                            read? Gates on illuminated fraction as well as
//                            altitude - the geometry doesn't care about phase,
//                            the photons do.
//   DOPPLER  (range-rate)  - is a frequency reference off the Moon (radar /
//                            moonbounce-EME / laser ranging) shifted, and by
//                            how much? Two additive geometric contributions:
//                            the Moon's own orbital range-rate (perigee <->
//                            apogee, ~27.3 days) plus the observer's own
//                            rotational velocity projected onto the line of
//                            sight (Earth's spin carries you toward the Moon's
//                            bearing on one side of the sky, away on the
//                            other - the dominant, fast-varying term, and the
//                            reason EME operators retune through a pass).
//                            Shares the bearing's az/alt geometry, so it
//                            shares the bearing's gate - same HORIZON_BAND,
//                            third channel, nothing new invented.
//
// INSTALL: paste this whole file into a new script in the Scriptable app,
// add a Scriptable widget to a Home Screen / Lock Screen, and point it at
// this script. Running it manually (not as a widget) presents a preview.
//
// AUDIT FIRST: this file does not carry its own self-test (Scriptable has no
// runner for one) - it is a direct line-by-line port of moon_lines.py, whose
// `python3 moon_lines.py` self-test is the audit. Trust this only as far as
// that passes, and re-check the port if you ever touch the math here.

// ---- degree-based trig (mirrors moon_lines.py 1:1) -------------------------
const sin   = (d) => Math.sin((d * Math.PI) / 180)
const cos   = (d) => Math.cos((d * Math.PI) / 180)
const tan   = (d) => Math.tan((d * Math.PI) / 180)
const asin  = (x) => (Math.asin(Math.max(-1, Math.min(1, x))) * 180) / Math.PI
const acos  = (x) => (Math.acos(Math.max(-1, Math.min(1, x))) * 180) / Math.PI
const atan2 = (y, x) => (Math.atan2(y, x) * 180) / Math.PI
const rev   = (d) => ((d % 360) + 360) % 360

// ---- gate thresholds (the only knobs; both are physical, not magic) --------
const HORIZON_BAND = 10.0 // deg above horizon below which parallax+refraction blur the fix
const ILLUM_MIN    = 0.10 // illuminated fraction below which the luminescent channel goes dark

// ---- physical constants for the Doppler channel (constants, not knobs) -----
const EARTH_RADIUS_KM  = 6371.0     // mean radius - converts geocentric distance and
                                    // rotation rate into real-world km and km/s
const SIDEREAL_DAY_S   = 86164.0905 // the clock Earth's spin actually runs on
const LIGHT_SPEED_KM_S = 299792.458 // c - converts a range-rate into a fractional shift

function dayNumber(dtUtc) {
  // Schlyter day number d: days since 2000 Jan 0.0 UT, with fraction.
  const Y = dtUtc.getUTCFullYear()
  const M = dtUtc.getUTCMonth() + 1
  const D = dtUtc.getUTCDate()
  const ut = dtUtc.getUTCHours() + dtUtc.getUTCMinutes() / 60 + dtUtc.getUTCSeconds() / 3600
  const d = 367 * Y - Math.floor((7 * (Y + Math.floor((M + 9) / 12))) / 4) +
            Math.floor((275 * M) / 9) + D - 730530
  return d + ut / 24
}

function solveKepler(M, e) {
  // Eccentric anomaly (deg) from mean anomaly M (deg), eccentricity e.
  let E = M + ((180 / Math.PI) * e * sin(M) * (1 + e * cos(M)))
  for (let i = 0; i < 6; i++) {
    const dE = (E - (180 / Math.PI) * e * sin(E) - M) / (1 - e * cos(E))
    E -= dE
    if (Math.abs(dE) < 1e-6) break
  }
  return E
}

function moonPosition(d) {
  // Geocentric apparent RA, Dec (deg) and distance (Earth radii) of the Moon,
  // plus ecliptic lon/lat and the Sun's longitude (for phase). Schlyter, with
  // the main perturbations.
  const w_s = 282.9404 + 4.70935e-5 * d
  const M_s = rev(356.047 + 0.9856002585 * d)
  const L_s = rev(w_s + M_s)

  const N = rev(125.1228 - 0.0529538083 * d)
  const i = 5.1454
  const w = rev(318.0634 + 0.1643573223 * d)
  const a = 60.2666
  const e = 0.0549
  const M = rev(115.3654 + 13.0649929509 * d)

  const E = solveKepler(M, e)
  const x = a * (cos(E) - e)
  const y = a * Math.sqrt(1 - e * e) * sin(E)
  let r = Math.hypot(x, y)
  const v = rev(atan2(y, x))

  const xe = r * (cos(N) * cos(v + w) - sin(N) * sin(v + w) * cos(i))
  const ye = r * (sin(N) * cos(v + w) + cos(N) * sin(v + w) * cos(i))
  const ze = r * (sin(v + w) * sin(i))
  let lon = rev(atan2(ye, xe))
  let lat = atan2(ze, Math.hypot(xe, ye))

  const Lm = rev(N + w + M)
  const Ms = M_s
  const Mm = M
  const Dl = rev(Lm - L_s)
  const F = rev(Lm - N)

  lon += -1.274 * sin(Mm - 2 * Dl) +
          0.658 * sin(2 * Dl) -
          0.186 * sin(Ms) -
          0.059 * sin(2 * Mm - 2 * Dl) -
          0.057 * sin(Mm - 2 * Dl + Ms) +
          0.053 * sin(Mm + 2 * Dl) +
          0.046 * sin(2 * Dl - Ms) +
          0.041 * sin(Mm - Ms) -
          0.035 * sin(Dl) -
          0.031 * sin(Mm + Ms) -
          0.015 * sin(2 * F - 2 * Dl) +
          0.011 * sin(Mm - 4 * Dl)
  lat += -0.173 * sin(F - 2 * Dl) -
          0.055 * sin(Mm - F - 2 * Dl) -
          0.046 * sin(Mm + F - 2 * Dl) +
          0.033 * sin(F + 2 * Dl) +
          0.017 * sin(2 * Mm + F)
  r += -0.58 * cos(Mm - 2 * Dl) - 0.46 * cos(2 * Dl)
  lon = rev(lon)

  const ecl = 23.4393 - 3.563e-7 * d
  const xg = r * cos(lon) * cos(lat)
  const yg = r * sin(lon) * cos(lat)
  const zg = r * sin(lat)
  const xq = xg
  const yq = yg * cos(ecl) - zg * sin(ecl)
  const zq = yg * sin(ecl) + zg * cos(ecl)
  const ra = rev(atan2(yq, xq))
  const dec = atan2(zq, Math.hypot(xq, yq))

  return { ra, dec, r, lon, lat, sunLon: L_s }
}

function localSiderealTime(d, lonEast, utHours) {
  const w_s = 282.9404 + 4.70935e-5 * d
  const M_s = rev(356.047 + 0.9856002585 * d)
  const L_s = rev(w_s + M_s)
  const gmst0Hours = (L_s + 180) / 15
  const gmstHours = gmst0Hours + utHours
  const lstHours = gmstHours + lonEast / 15
  return rev(lstHours * 15)
}

function doppler(d, latDeg, azDeg, altDeg) {
  // Topocentric range-rate (km/s) and the fractional shift it implies.
  // ORBITAL: centred numerical derivative of geocentric distance, +/-1h window.
  // ROTATIONAL: observer's eastward spin speed, projected onto the line of
  // sight (East-North-Up unit vector toward the Moon is
  // (sin(az)cos(alt), cos(az)cos(alt), sin(alt)); the observer's velocity is
  // purely eastward, so the dot product collapses to v_rot*sin(az)*cos(alt)).
  // Positive => spin carries the observer toward the Moon's bearing => closes
  // the range => SUBTRACTS from the rate of change of range.
  const DT_DAYS = 1 / 24
  const rMinus = moonPosition(d - DT_DAYS).r
  const rPlus = moonPosition(d + DT_DAYS).r
  const orbitalKmS = ((rPlus - rMinus) * EARTH_RADIUS_KM) / (2 * DT_DAYS * 86400)

  const vRot = ((2 * Math.PI * EARTH_RADIUS_KM) / SIDEREAL_DAY_S) * cos(latDeg)
  const rotationalKmS = -vRot * sin(azDeg) * cos(altDeg)

  const rangeRateKmS = orbitalKmS + rotationalKmS
  const oneWayPpb = (-rangeRateKmS / LIGHT_SPEED_KM_S) * 1e9
  const echoPpb = 2 * oneWayPpb

  return { rangeRateKmS, orbitalKmS, rotationalKmS, oneWayPpb, echoPpb }
}

function gateGeometry(alt) {
  if (alt < 0) return ['STOP', `Moon below horizon (${alt.toFixed(1)} deg). No bearing.`]
  if (alt < HORIZON_BAND)
    return ['HOLD', `Moon low (${alt.toFixed(1)} deg). Within the ${HORIZON_BAND.toFixed(0)} deg ` +
                    'horizon band where parallax+refraction blur the bearing ~1 deg.']
  return ['GO', `Moon clear of horizon (${alt.toFixed(1)} deg). Bearing trustworthy.`]
}

function gateLuminescent(alt, illum) {
  if (alt < 0) return ['STOP', 'Moon below horizon. No light reaching the sensor.']
  if (illum < ILLUM_MIN)
    return ['HOLD', `Moon up but nearly dark (${(illum * 100).toFixed(0)}% lit). ` +
                    'Too little lunar light to drive the luminescent read.']
  if (alt < HORIZON_BAND)
    return ['HOLD', `Moon lit (${(illum * 100).toFixed(0)}%) but low; light path grazes.`]
  return ['GO', `Moon up and lit (${(illum * 100).toFixed(0)}%). Luminescent read viable.`]
}

function gateDoppler(alt, rangeRateKmS) {
  // Same gate as the bearing: a clean Doppler read leans on the same az/alt
  // geometry as the compass, so the same horizon-band uncertainty blurs both.
  if (alt < 0) return ['STOP', 'Moon below horizon. No path - nothing to shift.']
  if (alt < HORIZON_BAND)
    return ['HOLD', `Moon low (${alt.toFixed(1)} deg); the same horizon-band blur ` +
                    'that softens the bearing softens the rotational term.']
  return ['GO', `Clear path; range-rate ${(rangeRateKmS * 1000).toFixed(0)} m/s is a clean read.`]
}

function phaseName(elong, waxing) {
  if (elong < 20) return 'new'
  if (elong < 70) return waxing ? 'waxing crescent' : 'waning crescent'
  if (elong < 110) return waxing ? 'first quarter' : 'last quarter'
  if (elong < 160) return waxing ? 'waxing gibbous' : 'waning gibbous'
  return 'full'
}

function compassPoint(az) {
  const pts = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
               'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
  return pts[Math.floor(((az + 11.25) % 360) / 22.5)]
}

function moonFix(latDeg, lonEastDeg, whenUtc, altitudeM) {
  // Full topocentric fix: bearing, altitude, phase, Doppler, and the
  // go/hold/stop gates - mirrors moon_lines.moon_fix() exactly.
  const d = dayNumber(whenUtc)
  const utHours = whenUtc.getUTCHours() + whenUtc.getUTCMinutes() / 60 + whenUtc.getUTCSeconds() / 3600
  const m = moonPosition(d)
  const lst = localSiderealTime(d, lonEastDeg, utHours)
  const H = rev(lst - m.ra)

  const altGeo = asin(sin(latDeg) * sin(m.dec) + cos(latDeg) * cos(m.dec) * cos(H))
  const aSouth = atan2(sin(H), cos(H) * sin(latDeg) - tan(m.dec) * cos(latDeg))
  const az = rev(aSouth + 180)

  const par = asin(1 / m.r)
  const alt = altGeo - par * cos(altGeo)

  const elong = acos(cos(m.lat) * cos(m.lon - m.sunLon))
  const illum = (1 - cos(elong)) / 2
  const waxing = rev(m.lon - m.sunLon) < 180

  const [geoVerdict, geoReason] = gateGeometry(alt)
  const [lumVerdict, lumReason] = gateLuminescent(alt, illum)
  const dop = doppler(d, latDeg, az, alt)
  const [dopVerdict, dopReason] = gateDoppler(alt, dop.rangeRateKmS)

  return {
    whenUtc,
    lat: latDeg, lonEast: lonEastDeg, altitudeM,
    azimuthDeg: az, altitudeDeg: alt,
    illumFrac: illum, phase: phaseName(elong, waxing),
    distanceEarthRadii: m.r,
    geometry: { verdict: geoVerdict, reason: geoReason },
    luminescent: { verdict: lumVerdict, reason: lumReason },
    doppler: { verdict: dopVerdict, reason: dopReason, ...dop },
  }
}

// ---- widget rendering -------------------------------------------------------
const GO_COLOR   = new Color('#5fd97a')
const HOLD_COLOR = new Color('#e8c547')
const STOP_COLOR = new Color('#e8625f')
const verdictColor = (v) => (v === 'GO' ? GO_COLOR : v === 'HOLD' ? HOLD_COLOR : STOP_COLOR)

function addChannelRow(stack, label, channel) {
  const row = stack.addStack()
  row.centerAlignContent()
  const dot = row.addText('●') // ●
  dot.font = Font.systemFont(11)
  dot.textColor = verdictColor(channel.verdict)
  row.addSpacer(6)
  const txt = row.addText(`${label}  ${channel.verdict}`)
  txt.font = Font.mediumSystemFont(11)
  txt.textColor = new Color('#d6e2f0')
  stack.addSpacer(3)
}

async function buildWidget() {
  const loc = await Location.current()
  const fix = moonFix(loc.latitude, loc.longitude, new Date(), loc.altitude || 0)
  const dp = fix.doppler

  const w = new ListWidget()
  w.backgroundColor = new Color('#0a1628')
  w.setPadding(14, 14, 14, 14)

  const title = w.addText('MOON COMPASS')
  title.font = Font.boldSystemFont(12)
  title.textColor = new Color('#7fa8d9')
  w.addSpacer(6)

  const bearing = w.addText(`${fix.azimuthDeg.toFixed(0)}°  ${compassPoint(fix.azimuthDeg)}`)
  bearing.font = Font.boldSystemFont(28)
  bearing.textColor = Color.white()

  const altLine = w.addText(
    `alt ${fix.altitudeDeg.toFixed(1)}°   ${fix.phase} (${(fix.illumFrac * 100).toFixed(0)}% lit)`
  )
  altLine.font = Font.systemFont(12)
  altLine.textColor = new Color('#a9bdd6')
  w.addSpacer(8)

  addChannelRow(w, 'COMPASS', fix.geometry)
  addChannelRow(w, 'LIGHT', fix.luminescent)
  addChannelRow(w, 'DOPPLER', fix.doppler)

  w.addSpacer(6)
  const dopLine = w.addText(
    `range-rate ${(dp.rangeRateKmS * 1000).toFixed(0)} m/s   ` +
    `${dp.oneWayPpb >= 0 ? '+' : ''}${dp.oneWayPpb.toFixed(1)} ppb 1-way   ` +
    `${dp.echoPpb >= 0 ? '+' : ''}${dp.echoPpb.toFixed(1)} ppb echo`
  )
  dopLine.font = Font.systemFont(9)
  dopLine.textColor = new Color('#7fa8d9')

  w.addSpacer(4)
  const stamp = w.addText(`fix ${fix.whenUtc.toISOString().slice(11, 16)} UTC`)
  stamp.font = Font.systemFont(8)
  stamp.textColor = new Color('#54719c')

  return w
}

const widget = await buildWidget()
if (config.runsInWidget) {
  Script.setWidget(widget)
} else {
  await widget.presentMedium()
}
Script.complete()
