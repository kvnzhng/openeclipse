# Build tools

`index.html` is generated. These are the scripts that generate it: they compute the
Sun/Moon ephemeris and the obscuration and path fields, pack them into a JSON bundle, and
inject that bundle into `sim_template.html` to write `../index.html`. There is no manual
copy step — `inject` writes the shipped file itself.

## Requirements

```bash
pip install -r requirements.txt
```

`ephem` ([PyEphem](https://rhodesmill.org/pyephem/)) supplies the geocentric apparent
positions of the Sun and Moon. `numpy` vectorises the grid computation. `pytest` runs the
test suite. All three are pinned exactly: the bundle is data, and a library update that
moved a position by an arcsecond would silently change the shipped numbers.

## Rebuilding

Run from inside this directory — every path is relative to the working directory.

```bash
python3 build_site.py all
```

That is the whole build: `fetch` → `build` → `inject`. It is also what you get with no
argument at all. The individual steps:

| Command | Does |
|---|---|
| `build_site.py fetch` | Downloads the Natural Earth 1:50m country polygons to `ne50.geojson` (~2.9 MB). Skipped if already present; a short file is rejected as truncated rather than half-built. |
| `build_site.py build` | Runs `build_data2.py` in a subprocess → `bundle.json` (583 KB). |
| `build_site.py inject` | Substitutes the bundle into `sim_template.html` at `__BUNDLE__` and writes **`../index.html`** directly. |
| `build_site.py extract` | The inverse: reads the bundle back off the `const B = …;` line of `../index.html` → `bundle.json`. |
| `build_site.py check` | Asserts `../index.html` == `sim_template.html` + `bundle.json`. Prints `ok`, or exits 1 naming the first line that differs. |

`build_data2.py` still works on its own — `python3 build_data2.py` writes `bundle.json`
exactly as `build` does — and it is not the slow step it once was. The grid pass is
vectorised over all 251 × 201 cells at once, so evaluating the geometry at every half-step
of the ephemeris for all three eclipses finishes in a few seconds.

### `extract` and `check`

Neither `ne50.geojson` nor `bundle.json` is committed, so a fresh clone has no bundle. You
do not have to re-run the astronomy to get one:

```bash
python3 build_site.py extract     # ../index.html -> bundle.json
```

`inject` and `extract` are exact inverses, escaping included, so this recovers the shipped
bundle byte for byte.

`check` is the guard on the one real hazard in this layout. `sim_template.html` is the
source of the frontend and `../index.html` is generated from it, so **an edit made to
`index.html` directly will be silently reverted by the next `inject`** — always edit the
template. Run `check` before shipping:

```bash
$ python3 build_site.py check
ok: ../index.html == sim_template.html + bundle.json (751 KB)
```

On drift it names the line, which tells you immediately whether the template moved ahead of
the page or the other way round.

## The files

| File | Role |
|---|---|
| `eclipse.py` | The circumstance engine, and the reference implementation the JavaScript is a port of. Run it directly for the A Coruña validation case. |
| `build_data.py` | First-generation bundle builder. **Superseded**, but `build_data2.py` imports its helpers (`ephem_row`, `sep_grid`, `obsc`, `simplify`), so it is a live dependency, not dead code. It is a function library only now: running it directly exits 1 and points you at `build_data2.py`, because the bundle it used to write (Iberia-only grid, no band field) is no longer one the template can read. |
| `build_data2.py` | The current builder: continental coverage and the signed-clearance band field. The work lives in `main()` behind a `__main__` guard, so it can be imported or driven by `build_site.py build` as well as run. |
| `build_site.py` | The pipeline driver: `fetch`, `build`, `inject`, `extract`, `check`, `all`. |
| `test_eclipse.py` | The pytest suite over `eclipse.py` and the injection escaping. |
| `solar.py` | Standalone NOAA solar-position model. **Not part of this pipeline** — it was used to validate solar altitudes against IGN's published figures while the project was being built. Kept because it is the independent check behind those numbers. |
| `sim_template.html` | The frontend source: `index.html` with the data replaced by `__BUNDLE__`. Edit this, never `../index.html`. |

## Validating

```bash
python3 eclipse.py
```

Computes contacts for A Coruña (43.38, −8.41) on 12 August 2026 from scratch and prints
them against a reference application's published values:

```
==============================================================
VALIDATION  43.38, -8.41  ·  12 Aug 2026  ·  times CEST
==============================================================
  C1 first contact     19:30:51   app says 19:30:48   Δ +3s
  C2 totality begins   20:27:34   app says 20:26:59   Δ +35s
  Maximum              20:28:13   app says 20:27:39   Δ +34s
  C3 totality ends     20:28:52   app says 20:28:19   Δ +33s
  C4 last contact      21:21:54   app says 21:21:49   Δ +5s

  totality duration  77.5s   app says 80s
  max obscuration    100.0%
  sun altitude       12.04°   azimuth 279.1°

  at 20:08:06 CEST → obsc 57.25%  mag 0.652   app says 57.44% / 0.654
```

The altitude is apparent, not geometric — `refract()` applies Saemundsson's (1986)
geometric → apparent formula. Refraction touches altitude only, so every contact time
above is unchanged by it. The JavaScript `refract()` in `sim_template.html` is the same
formula with the same clamp, so the two implementations still agree term for term.

C1, C4, obscuration and magnitude agree closely. The ~34 s offset through the central
phase is expected at this particular pin: A Coruña sits near the umbral edge, where
closest approach is about 24″ against a 33″ threshold, so the time of maximum is
ill-conditioned. Inside the path the ambiguity disappears. See
[../SOURCES.md](../SOURCES.md) for the full validation record.

## Testing

```bash
python3 -m pytest . -q        # from this directory
python3 -m pytest tools/ -q   # or from the repo root
```

33 tests over `eclipse.py` and the injection escaping, in under a second. They cover the A
Coruña circumstances above as a golden case, the branches and boundaries of
`obscuration()` (including a Monte-Carlo cross-check of the lens area), `refract()` pinned
as Saemundsson with a Bennett round-trip and the clamp behaviour, `eclipse.py`'s scalar
`obscuration()` against `build_data.py`'s vectorised `obsc()` twin, `solve()`'s trailing
partial step, and the `<script>` escaping that `inject` and `extract` depend on.

`.github/workflows/tests.yml` runs the same command on every push and pull request.

## One deliberate inconsistency

It is in the original scripts and is left as it is, because changing it would alter the
shipped numbers:

**`eclipse.py` uses `K_MOON = 1737.4`; `build_data.py` uses `1738.09`.** The shipped
JavaScript uses 1738.09 (`k = 0.2725076`, the standard value for eclipse prediction). So
`eclipse.py` is a near-but-not-exact check on the shipped engine rather than an identical
one — it predicts a marginally smaller Moon and therefore a slightly shorter totality
(77.5 s against the shipped engine's 79.5 s at A Coruña). Everything else in `eclipse.py`
— the constants, the topocentric reduction, the obscuration formula and `refract()` — is
term-for-term the same as the JavaScript.
