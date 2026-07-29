# Sources and validation

Everything openEclipse displays is computed from the sources below by the scripts in
[`tools/`](tools/). Nothing is fetched at runtime and no figures are transcribed from
published tables — the published values appear only as validation targets.

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
| Sun altitude at maximum | 11.96° | — | — |

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
- **No atmospheric refraction** in the simulator's altitude readout — it is geometric
  altitude. (`solar.py` does model refraction, but it is not part of the pipeline.)
- **No place-name geocoding.** Presets and latitude/longitude entry only.
- **ΔT** is handled inside PyEphem at build time; the browser does no time-scale
  conversion.

## Licence

The code is MIT (see [LICENSE](LICENSE)). Natural Earth data is public domain. PyEphem
is LGPL and is a build-time dependency only — it is not redistributed in `index.html`,
which contains only computed numeric output.
