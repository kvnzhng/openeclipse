# How openEclipse works

openEclipse is a single HTML file with no build step and no network calls. Everything
below happens either at build time (in a Python engine, offline) or in your browser as
you move the pin.

## The central design decision

Eclipse prediction splits cleanly into two halves:

| | Depends on the observer? | Cost | Where it runs |
|---|---|---|---|
| Sun & Moon positions | No — same for everyone | High | **Precomputed in Python, embedded as a table** |
| Parallax, disc overlap, contact times | Yes — different every metre | Low | **Computed live in JavaScript** |

So the astronomy is tabulated and the geometry is solved. Precomputing the ephemeris
avoids doing orbital mechanics in JavaScript; computing the topocentric geometry live is
what lets the readouts respond to a pin dragged a few kilometres.

## The embedded data

One JSON object, `const B`, at [`index.html:205`](index.html#L205) — about 596 KB of the
616 KB file.

| Key | Shape | Contents |
|---|---|---|
| `events[k].eph` | 181 / 151 / 166 rows × 7 floats | Geocentric Sun & Moon ephemeris |
| `events[k].obsc` | 50,451 bytes, base64 | Maximum-obscuration field |
| `events[k].band` | 50,451 bytes, base64 | Path of totality / annularity |
| `events[k].line` | 116 / 276 / 93 points | Centreline |
| `grid` | 251 × 201 at 0.3° | Grid covering lon −30°…45°, lat 10°…70° |
| `coast` | 250 polylines | Coastlines |

Three events are bundled: 12 Aug 2026 (total), 2 Aug 2027 (total), 26 Jan 2028 (annular).

### The ephemeris table

Each row is sampled every 2 minutes and holds seven values, destructured at
[`index.html:250`](index.html#L250):

```js
const [sra, sdec, sr, mra, mdec, mr, gast] = eph(minUTC);
```

— Sun right ascension, declination and distance; the same three for the Moon; and
Greenwich Apparent Sidereal Time. Distances are in Earth radii, angles in degrees. The
tables span 5–6 hours around each eclipse, which is the only window the app can display.

### Grid encoding

Both grids are one byte per cell, stored **south-up** and flipped when the image is built
([`index.html:366`](index.html#L366)).

- `obsc`: byte ÷ 254 gives obscuration in 0…1.
- `band`: a *signed clearance* from the central-eclipse limit. 128 is exactly on the
  limit and one unit is 0.01 arcmin, so the edge of the path can be drawn with a soft
  antialiased falloff rather than a hard stair-stepped boundary
  ([`index.html:378`](index.html#L378)).

## The runtime pipeline

### 1. Interpolation — `eph(minUTC)`

[`index.html:236`](index.html#L236). Four-point Lagrange interpolation across the
2-minute samples, so any instant is available rather than only multiples of 2 minutes.
The Moon moves about 0.5°/hour, so cubic interpolation over a 2-minute window is far
below the precision that matters here.

### 2. Topocentric correction — `circ(minUTC, lat, lon)`

[`index.html:249`](index.html#L249). The most important step. It builds the observer's
position on an oblate Earth,

```js
const u  = Math.atan(FLAT * Math.tan(phi));
const rc = Math.cos(u), rs = FLAT * Math.sin(u);
```

then subtracts that vector from the geocentric Sun and Moon vectors to get *topocentric*
right ascension, declination and distance.

This is not a refinement — it is the whole reason the app can tell you anything specific.
The Moon's horizontal parallax is roughly 1°, against discs only about 0.5° wide. A
geocentric calculation would place the eclipse in the wrong part of the world.

Apparent semi-diameters come from the resulting distances:

```js
s1 = asin(K_SUN  / (S.d · R_E))      // Sun
s2 = asin(K_MOON / (M.d · R_E))      // Moon
```

Whether the eclipse is total or annular at your location falls straight out of this as
`s2 < s1` — the Moon's disc being the smaller of the two.

### 3. Magnitude and obscuration

[`index.html:282`](index.html#L282) and [`index.html:288`](index.html#L288). Both are
closed-form, no lookup.

**Magnitude** — the fraction of the Sun's *diameter* covered:

```
sep ≥ s1 + s2      → 0                    (no contact)
sep ≤ |s1 − s2|    → s2 / s1              (one disc wholly inside the other)
otherwise          → (s1 + s2 − sep) / 2·s1
```

**Obscuration** — the fraction of the Sun's *area* covered, as the exact
circle-circle overlap summed from two circular segments:

```
(a²(θ₁ − sin 2θ₁ / 2) + b²(θ₂ − sin 2θ₂ / 2)) / π·a²
```

with θ₁ and θ₂ from the law of cosines on the triangle joining the two disc centres.

### 4. Contact times — `findContacts(lat, lon)`

[`index.html:298`](index.html#L298). Two functions change sign at the four contacts:

- `sep − (s1 + s2)` → C1 and C4 (partial phase begins / ends)
- `sep − |s1 − s2|` → C2 and C3 (totality or annularity begins / ends)

The app sweeps the whole window at 15-second steps looking for sign changes, then
**bisects 44 times** on each bracket — which converges to floating-point precision, well
past the displayed second. Maximum eclipse is then refined with a **50-iteration
golden-section search** on the separation minimum ([`index.html:316`](index.html#L316)).

The times in the stats bar are therefore solved numerically, in your browser, for your
exact coordinates. Clicking one seeks the timeline to it.

### 5. The panes

**Map** — equirectangular, with the longitude scale fixed at `cos 40°`
([`index.html:387`](index.html#L387)) so panning north or south doesn't squeeze the
image. The obscuration field and path are drawn as cached offscreen canvases built once
per event.

**Sky** — `buildTrack()` at [`index.html:451`](index.html#L451) samples `circ()` every
2 minutes across the window to trace the Sun and Moon paths, then draws the pair at the
current instant. The horizon-obstruction slider is a flat altitude cut-off; no terrain
data is bundled, which the panel says plainly.

## Accuracy and limits

- **Time window.** Only the 5–6 hours around each of the three bundled eclipses exist.
  There is no general-purpose ephemeris.
- **Map coverage is regional; readouts are global.** The colour field and path overlay
  only exist inside the embedded grid box (lon −30°…45°, lat 10°…70°). The pin
  calculations don't touch that grid at all — `circ()` and `findContacts()` are pure
  geometry from the ephemeris, so dropping a pin anywhere on Earth still gives correct
  numbers, including a correct 0% where the eclipse isn't visible.
- **Grid resolution.** 0.3° is roughly 33 km, so the map's colours are a smooth
  approximation. Drag the pin a short distance and the totality duration will change
  while the background colour does not — the readouts are the finer instrument.
- **No atmospheric refraction.** `altaz()` returns geometric altitude. Near the horizon
  the true apparent altitude is higher by up to about half a degree.
- **No terrain.** The horizon-obstruction slider is yours to set.
- **ΔT** (the difference between Terrestrial and Universal Time) is not handled in the
  browser; it is baked into the precomputed ephemeris.

## Adopted constants

[`index.html:208`](index.html#L208):

| Constant | Value | Meaning |
|---|---|---|
| `R_E` | 6378.137 km | Earth equatorial radius (WGS-84) |
| `FLAT` | 0.99664719 | Polar / equatorial axis ratio (WGS-84) |
| `K_SUN` | 696000 km | Adopted solar radius |
| `K_MOON` | 1738.09 km | Adopted lunar radius — `k = 0.2725076`, the standard value for total and annular eclipse prediction |

## Source map

| Concern | Location |
|---|---|
| Constants | [`index.html:208`](index.html#L208) |
| Embedded data `B` | [`index.html:205`](index.html#L205) |
| Ephemeris interpolation | [`index.html:236`](index.html#L236) |
| Topocentric circumstances | [`index.html:249`](index.html#L249) |
| Magnitude / obscuration | [`index.html:282`](index.html#L282) |
| Contact solving | [`index.html:298`](index.html#L298) |
| Grid decode & colouring | [`index.html:354`](index.html#L354) |
| Map projection | [`index.html:387`](index.html#L387) |
| Sky track | [`index.html:451`](index.html#L451) |
| Stats & timeline refresh | [`index.html:640`](index.html#L640) |
