# Sources and validation

Everything openEclipse displays is computed from the sources below by the scripts in
[`tools/`](tools/). No figures are transcribed from published tables — the published
values appear only as validation targets. Place search is the sole runtime network call;
every computed quantity is derived from data embedded at build time.

## Astronomical data

**Sun and Moon positions — [PyEphem](https://rhodesmill.org/pyephem/) (`ephem`).**
Geocentric *apparent* right ascension, declination and distance, via `ephem.Sun()` /
`ephem.Moon()` and the `g_ra`, `g_dec`, `earth_distance` attributes. Greenwich apparent
sidereal time comes from an `ephem.Observer()` at 0°, 0°. PyEphem is the Python binding
to the XEphem `libastro` library. See [`tools/build_data.py`](tools/build_data.py)
`ephem_row()`.

> A note on provenance: the development log for this project describes the ephemeris as
> "JPL-derived". That is loose. PyEphem evaluates analytical series in `libastro`; it is
> not a JPL kernel and does not read DE-series binary ephemerides. The accuracy is more
> than sufficient here — the validation below bears that out — but if you need
> kernel-grade positions, swap `ephem_row()` for Skyfield with a JPL DE kernel and
> rebuild.

**Coastlines — [Natural Earth](https://www.naturalearthdata.com/), 1:50m admin-0
countries.** Fetched from the
[nvkelso/natural-earth-vector](https://github.com/nvkelso/natural-earth-vector)
mirror by [`tools/build_site.py`](tools/build_site.py). Natural Earth is public domain.
Rings are simplified with Ramer–Douglas–Peucker at ε = 0.05°.

**Solar altitude cross-check — NOAA solar position algorithm**, implemented
independently in [`tools/solar.py`](tools/solar.py) and used to verify altitudes against
published figures from Spain's
[Instituto Geográfico Nacional (IGN)](https://www.ign.es/).

**Place search — [Photon](https://photon.komoot.io/) (komoot, OpenStreetMap data)**, with
**[Open-Meteo geocoding](https://open-meteo.com/en/docs/geocoding-api)** as a fallback.
Both are keyless and CORS-open; neither is bundled, and both are queried only when you
type in the search box. A key was disqualified by the fact that `index.html` is public.

**Atmospheric refraction — Bennett (1982)**, `R = 1/tan(h + 7.31/(h + 4.4))` arcminutes,
as given in Meeus, *Astronomical Algorithms*, ch. 16. Applied to altitudes only, so
contact times and obscuration are unaffected. See
[HOW-IT-WORKS.md](HOW-IT-WORKS.md#6-atmospheric-refraction).

## Adopted constants

Defined in [`tools/build_data.py`](tools/build_data.py) and mirrored in the JavaScript.

| Constant | Value | Source |
|---|---|---|
| Earth equatorial radius | 6378.137 km | WGS-84 |
| Polar / equatorial axis ratio | 0.99664719 | WGS-84 (1 − 1/298.257223563) |
| Solar radius | 696 000 km | Adopted standard value |
| Lunar radius | 1738.09 km | `k = 0.2725076`, the IAU value adopted for total and annular eclipse prediction |
| Astronomical unit | 149 597 870.7 km | IAU 2012 definition |

## Validation record

These are checks recorded during development. Contact times, altitude and obscuration
are reproducible now by running `python3 eclipse.py` from `tools/`; the geographic and
duration checks were run against intermediate build artifacts and are reported as
logged.

### Reproducible here

A Coruña (43.38, −8.41), 12 August 2026, against a published reference application:

| Quantity | Computed | Reference | Δ |
|---|---|---|---|
| C1 first contact | 19:30:51 | 19:30:48 | +3 s |
| C4 last contact | 21:21:54 | 21:21:49 | +5 s |
| Obscuration at 20:08:06 CEST | 57.25 % | 57.44 % | −0.19 pt |
| Magnitude at 20:08:06 CEST | 0.652 | 0.654 | −0.002 |
| Sun altitude at maximum (apparent) | 12.04° | — | — |

Refraction was added after this table was first recorded. It changes altitudes only —
the contact times, obscuration and magnitude above are byte-identical before and after,
which is the regression test for that change. The altitude at A Coruña moved from 11.96°
geometric to 12.04° apparent.

At low altitudes the effect is decisive rather than cosmetic. For 26 January 2028:

| Site | Geometric | Apparent | |
|---|---|---|---|
| Palma | −0.11° | **+0.49°** | below → above the horizon |
| Girona | −1.03° | −0.19° | still below, but marginal |
| Valencia | +2.14° | +2.43° | |

### Recorded during development

| Check | Computed | Published |
|---|---|---|
| Cádiz 2028 — Sun altitude | 7.8° | 7.8° |
| Cádiz 2028 — annularity duration | 6 m 38 s | 6 m 37 s |
| Seville 2028 — annularity duration | 7 m 12 s | 7 m 08 s |
| Tarifa 2027 — totality duration | 4 m 42 s | ≈ 4 m 39 s |
| Madrid 2028 — obscuration | 82.3 % | ≈ 82 % |
| 2026 path width | ≈ 290 km | ≈ 290 km |
| A Coruña — solar altitude vs IGN | 12.1° | 12° |
| Palma — solar altitude vs IGN | 2.6° | 2° |
| Cape Town, 2026 | no contacts, 0 % | correct — not visible |

Greatest-eclipse magnitudes for the bundled events are 1.0386 (2026) and 1.0790 (2027);
computed values at specific sites sit just below these, as expected away from the point
of greatest eclipse.

A geographic test of 17 sites against their true in-path / out-of-path status passes for
all 17, including Luxor for 2027.

### Known discrepancy

At A Coruña the central-phase times (C2, maximum, C3) come out ~34 s later than the
reference application, while C1 and C4 agree within 5 s. That pin sits close to the
umbral edge — closest approach about 24″ against a 33″ threshold — where the time of
maximum is genuinely ill-conditioned and small differences in adopted lunar radius or
ephemeris move it disproportionately. Well inside the path the ambiguity disappears.

Note also that `eclipse.py` adopts a lunar radius of 1737.4 km while the shipped engine
uses 1738.09 km, so it is a close but not identical check. See
[`tools/README.md`](tools/README.md).

## What is *not* sourced

- **No terrain.** The horizon-obstruction slider is user input, not a DEM-derived
  skyline. No elevation data is bundled.
- **Refraction is modelled for a standard atmosphere only.** Bennett's formula assumes
  10 °C and 1010 mb; real near-horizon refraction varies by several arcminutes with
  temperature, pressure and inversion layers. Near-horizon verdicts are marginal.
- **Place search depends on a third party.** Names and coordinates come from Photon or
  Open-Meteo at runtime, not from anything bundled, so search needs a connection and
  inherits whatever those services get wrong. The eclipse figures for whatever point it
  returns are still computed locally.
- **ΔT** is handled inside PyEphem at build time; the browser does no time-scale
  conversion.

## Licence

The code is MIT (see [LICENSE](LICENSE)). Natural Earth data is public domain. PyEphem
is LGPL and is a build-time dependency only — it is not redistributed in `index.html`,
which contains only computed numeric output.
