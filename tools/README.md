# Build tools

`index.html` is generated. These are the scripts that generate it: they compute the
Sun/Moon ephemeris and the obscuration and path fields, pack them into a JSON bundle,
and inject that bundle into the HTML template.

## Requirements

```bash
pip install -r requirements.txt
```

`ephem` ([PyEphem](https://rhodesmill.org/pyephem/)) supplies the geocentric apparent
positions of the Sun and Moon. `numpy` vectorises the grid computation.

## Rebuilding

Run from inside this directory — the scripts read and write relative to the working
directory.

```bash
python3 build_site.py fetch
```

Downloads the Natural Earth 1:50m country polygons to `ne50.geojson` (~25 MB). Skipped
if the file is already present.

```bash
python3 build_data2.py
```

Computes everything and writes `bundle.json` (~580 KB). This is the slow step: it
evaluates the topocentric geometry over a 251 × 201 grid at every half-step of the
ephemeris, for all three eclipses.

```bash
python3 build_site.py inject
```

Substitutes the bundle into `sim_template.html` at the `__BUNDLE__` placeholder and
writes `openeclipse-simulator.html`. Copy that over `../index.html` to ship it:

```bash
cp openeclipse-simulator.html ../index.html
```

`sim_template.html` is the current `index.html` with the data blob replaced by
`__BUNDLE__`, and is kept in sync with it — template plus bundle reproduces the shipped
file byte for byte. **If you edit `index.html` directly, mirror the change into
`sim_template.html`**, or the next rebuild will silently revert it.

## The files

| File | Role |
|---|---|
| `eclipse.py` | The circumstance engine, and the reference implementation the JavaScript is a port of. Run it directly for the A Coruña validation case. |
| `build_data.py` | First-generation bundle builder. **Superseded**, but `build_data2.py` imports its helpers (`ephem_row`, `sep_grid`, `obsc`, `simplify`), so it is a live dependency, not dead code. Running it directly still produces the older Iberia-only bundle. |
| `build_data2.py` | The current builder: continental coverage and the signed-clearance band field. |
| `build_site.py` | Fetches coastlines and injects the bundle into the template. |
| `solar.py` | Standalone NOAA solar-position model. **Not part of this pipeline** — it was used to validate solar altitudes against IGN's published figures while the project was being built. Kept because it is the independent check behind those numbers. |
| `sim_template.html` | `index.html` with the data replaced by `__BUNDLE__`. |

## Validating

```bash
python3 eclipse.py
```

Computes contacts for A Coruña (43.38, −8.41) on 12 August 2026 from scratch and prints
them against a reference application's published values:

```
C1 first contact     19:30:51   app says 19:30:48   Δ +3s
C2 totality begins   20:27:34   app says 20:26:59   Δ +35s
Maximum              20:28:13   app says 20:27:39   Δ +34s
C3 totality ends     20:28:52   app says 20:28:19   Δ +33s
C4 last contact      21:21:54   app says 21:21:49   Δ +5s
sun altitude         12.04°   azimuth 279.1°
at 20:08:06 CEST → obsc 57.25%  mag 0.652   app says 57.44% / 0.654
```

The altitude is apparent, not geometric — `refract()` applies Bennett's formula, mirroring
the JavaScript. Refraction touches altitude only, so every contact time above is
unchanged by it.

C1, C4, obscuration and magnitude agree closely. The ~34 s offset through the central
phase is expected at this particular pin: A Coruña sits near the umbral edge, where
closest approach is about 24″ against a 33″ threshold, so the time of maximum is
ill-conditioned. Inside the path the ambiguity disappears. See
[../SOURCES.md](../SOURCES.md) for the full validation record.

## Two known inconsistencies

Both are in the original scripts and are left as they are, because changing them would
alter the shipped numbers:

- **`eclipse.py` uses `K_MOON = 1737.4`; `build_data.py` uses `1738.09`.** The shipped
  JavaScript uses 1738.09 (`k = 0.2725076`, the standard value for eclipse prediction).
  So `eclipse.py` is a near-but-not-exact check on the shipped engine rather than an
  identical one — it predicts a marginally smaller Moon and therefore a slightly shorter
  totality (77.5 s against the app's 79 s at A Coruña).
- **`eclipse.py` had a double timezone shift** in its final spot-check, subtracting two
  hours from a time already given in UTC and so sampling 16:08 instead of 18:08. It
  reported 0.00 % obscuration. Fixed; it now reports 57.25 %.
