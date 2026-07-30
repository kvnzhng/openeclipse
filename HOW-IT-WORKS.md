# How openEclipse works

openEclipse ships as a single HTML file with no subresources: no stylesheet, no script
and no font is fetched from anywhere, because the two webfonts are embedded as base64
`woff2` data URIs alongside the data. Opening the page therefore makes **zero** network
requests. Place search is the one feature that calls out at all — see
[Place search](#place-search) — and everything else works with no connection: the eclipse
maths, the map, the presets, and lat/lon entry. Everything below happens either at build
time, in the Python pipeline under [`tools/`](tools/), or in your browser as you move the
pin.

The build side is documented in [`tools/README.md`](tools/README.md); the data sources
and validation record are in [`SOURCES.md`](SOURCES.md).

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

One JSON object, `const B`, at [`index.html:393`](index.html#L393) — about 583 KB of the
752 KB file. Most of what is left is the two embedded fonts (101 KB); the markup, CSS and
JavaScript together come to about 68 KB.

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
[`index.html:451`](index.html#L451):

```js
const [sra, sdec, sr, mra, mdec, mr, gast] = eph(minUTC);
```

— Sun right ascension, declination and distance; the same three for the Moon; and
Greenwich Apparent Sidereal Time. Distances are in Earth radii, angles in degrees. The
tables span 5–6 hours around each eclipse, which is the only window the app can display.

### Grid encoding

Both grids are one byte per cell, stored **south-up** and flipped when the image is built
([`index.html:624`](index.html#L624)).

- `obsc`: byte ÷ 254 gives obscuration in 0…1.
- `band`: a *signed clearance* from the central-eclipse limit. 128 is exactly on the
  limit and one unit is 0.01 arcmin, so the edge of the path can be drawn with a soft
  antialiased falloff rather than a hard stair-stepped boundary
  ([`index.html:637`](index.html#L637)).

## The runtime pipeline

### 1. Interpolation — `eph(minUTC)`

[`index.html:423`](index.html#L423). Four-point Lagrange interpolation across the
2-minute samples, so any instant is available rather than only multiples of 2 minutes.
The Moon moves about 0.5°/hour, so cubic interpolation over a 2-minute window is far
below the precision that matters here.

### 2. Topocentric correction — `circ(minUTC, lat, lon)`

[`index.html:450`](index.html#L450). The most important step. It builds the observer's
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

[`index.html:483`](index.html#L483) and [`index.html:489`](index.html#L489). Both are
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

[`index.html:499`](index.html#L499). Two functions change sign at the four contacts:

- `sep − (s1 + s2)` → C1 and C4 (partial phase begins / ends)
- `sep − |s1 − s2|` → C2 and C3 (totality or annularity begins / ends)

The app sweeps the whole window at 15-second steps looking for sign changes, then
**bisects 44 times** on each bracket — which converges to floating-point precision, well
past the displayed second. Maximum eclipse is then refined with a **50-iteration
golden-section search** on the separation minimum ([`index.html:519`](index.html#L519)).

A totality shorter than the 15-second scan step can fall entirely between two samples, so
the sweep sees no C2/C3 even though the refined maximum is plainly central — exactly the
case for a pin on the edge of the path. When that happens the solver walks outwards from
the maximum in single steps until the C2/C3 function turns positive again and bisects
inside that bracket ([`index.html:529`](index.html#L529)), so durations stay continuous
down to a fraction of a second instead of snapping to zero.

The times in the stats bar are therefore solved numerically, in your browser, for your
exact coordinates. Clicking one seeks the timeline to it.

### 5. The panes

**Map** — equirectangular, with the longitude scale fixed at `cos 40°`
([`index.html:645`](index.html#L645)) so panning north or south doesn't squeeze the
image. The obscuration field and path are drawn as cached offscreen canvases built once
per event.

### 6. Atmospheric refraction

Altitudes are **apparent**, not geometric. `refract()`
([`index.html:444`](index.html#L444)) applies Saemundsson's (1986) formula,

```
R = 1.02 / tan(h + 10.3/(h + 5.11))    R in arcminutes, h in degrees
```

which lifts the Sun by about 29′ at the horizon, 5.4′ at 10°, and under 2′ above 30°.

The direction of the formula matters more than it looks. Bennett's better-known (1982)
`R = 1/tan(h + 7.31/(h + 4.4))` is defined the other way round — it takes an *apparent*
altitude and returns the true one — so handing it a geometric altitude overestimates
refraction, by 5.5′ at the horizon. Saemundsson is its geometric → apparent companion:
compose the two and you come back to where you started, to within 0.06′ anywhere above the
horizon.

The series turns over just above −2° and blows up at −5.11°, so the argument is clamped at
−2°; refraction saturates instead of misbehaving, keeping apparent altitude continuous and
monotonic for tracks that dip below the horizon.

It is applied to altitude only — **never** to the separation the contacts are solved on.
The Sun and Moon are within half a degree of each other and refract almost identically,
so contact times and obscuration are unaffected. Applying it to both bodies separately
does reproduce the flattening of a low Sun, which is what you actually see.

This matters most where the app is most useful. For the 26 January 2028 annular eclipse,
Palma's geometric altitude at maximum is −0.11° but its apparent altitude is +0.39° — about
a solar radius and a half, which is enough to lift the whole ring clear of the horizon,
reversing the answer to the question the horizon tool exists to ask.

**Sky** — `buildTrack()` at [`index.html:714`](index.html#L714) samples `circ()` every
2 minutes across the window to trace the Sun and Moon paths, then draws the pair at the
current instant. The horizon-obstruction slider is a flat altitude cut-off; no terrain
data is bundled, which the panel says plainly.

## Live sync

`tMin` is minutes UTC within the eclipse day, so SYNC does all of its comparison in UTC:
`getUTCHours()` and friends give the correct instant wherever the viewer is, which is what
makes the check timezone-proof. Times shown back to the user are then formatted through
`clockStr()` in whichever offset they have selected, so the dialog quotes the window in
their terms rather than in UTC.

It is enabled only when today's UTC date matches the event date *and* the current UTC
minute falls inside the observable window at the current pin. Otherwise the button opens a
dialog naming the window and the current local time.

While synced the animation loop reads the wall clock every frame rather than accumulating
elapsed time, so it cannot drift away from the real eclipse over a long session. Any
manual control — scrub, play, speed, the jump buttons, a contact-time click, or switching
event — drops out of sync.

## Place search

The only part of the app that touches the network, and only while you type. Typing two or
more characters queries a geocoder, debounced by 300 ms; picking a result sets the pin's
latitude and longitude and recentres the map on it.

**What leaves the page.** Exactly one thing: the text you typed, as a URL query parameter
to Photon (`?q=`) or, on fallback, to Open-Meteo (`?name=`). Nothing else is sent — not the
pin's coordinates, not which eclipse you are looking at, not the time on the scrubber.
Nothing is sent before the second character, and nothing at all is sent if you use the
presets or the lat/lon boxes. Those two hosts, plus the GitHub and OpenStreetMap links in
the footer, are the only URLs in the file.

Two keyless, CORS-open services are used, in order:

1. **[Photon](https://photon.komoot.io/)** (komoot, OpenStreetMap data) — built for
   type-ahead, and covers arbitrary places rather than only settlements, so airports,
   landmarks and streets resolve.
2. **[Open-Meteo geocoding](https://open-meteo.com/en/docs/geocoding-api)** — used only if
   Photon is unreachable. GeoNames-based, so towns and cities but not arbitrary features.

Neither needs an API key, which matters: `index.html` is served publicly, so any key in it
would be readable by anyone.

Three details worth knowing:

- **Stale responses cannot win.** Each request carries a sequence number and a reply is
  discarded if a newer keystroke has already fired, so fast typing can't leave you looking
  at results for a prefix you have moved past.
- **Result text is escaped, not trusted.** Names come from a third party and go through
  `esc()` before reaching `innerHTML`.
- **Failure is graceful.** If both services are unreachable the list shows *Search
  unavailable*, and the curated presets and lat/lon entry keep working — so the app is
  still fully usable offline, just without search.

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
- **Refraction is a standard-atmosphere model.** Saemundsson's formula assumes 10 °C and
  1010 mb. Real refraction near the horizon varies with temperature, pressure and
  inversion layers by several arcminutes — more than the difference between one published
  refraction formula and the next — so an altitude quoted as +0.2° is genuinely uncertain.
  Treat near-horizon verdicts as marginal rather than definitive.
- **No terrain.** The horizon-obstruction slider is yours to set.
- **ΔT** (the difference between Terrestrial and Universal Time) is not handled in the
  browser; it is baked into the precomputed ephemeris.

## Adopted constants

[`index.html:396`](index.html#L396):

| Constant | Value | Meaning |
|---|---|---|
| `R_E` | 6378.137 km | Earth equatorial radius (WGS-84) |
| `FLAT` | 0.99664719 | Polar / equatorial axis ratio (WGS-84) |
| `K_SUN` | 696000 km | Adopted solar radius |
| `K_MOON` | 1738.09 km | Adopted lunar radius — `k = 0.2725076`, the standard value for total and annular eclipse prediction |

## Source map

| Concern | Location |
|---|---|
| Constants | [`index.html:396`](index.html#L396) |
| Embedded data `B` | [`index.html:393`](index.html#L393) |
| Ephemeris interpolation | [`index.html:423`](index.html#L423) |
| Refraction | [`index.html:444`](index.html#L444) |
| Topocentric circumstances | [`index.html:450`](index.html#L450) |
| Magnitude / obscuration | [`index.html:483`](index.html#L483) |
| Contact solving | [`index.html:499`](index.html#L499) |
| Grid decode & colouring | [`index.html:612`](index.html#L612) |
| Map projection | [`index.html:645`](index.html#L645) |
| Sky track | [`index.html:714`](index.html#L714) |
| Stats & timeline refresh | [`index.html:992`](index.html#L992) |
