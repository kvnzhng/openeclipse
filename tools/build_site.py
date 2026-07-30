"""Companion helper: fetch the coastlines, run the data build, ship the HTML.

    python3 build_site.py fetch      # download the Natural Earth coastlines
    python3 build_site.py build      # -> bundle.json (runs build_data2.py)
    python3 build_site.py inject     # bundle.json + template -> ../index.html
    python3 build_site.py extract    # ../index.html -> bundle.json (inverts inject)
    python3 build_site.py check      # template + bundle == ../index.html? exit 1 on drift
    python3 build_site.py all        # fetch -> build -> inject

Run it from inside this directory: every path is relative to the working directory.
"""
import json
import os
import subprocess
import sys
import urllib.request

# Pinned to the v5.1.2 tag: on master the country NAME values that the keep-lists
# in build_data*.py match on can change under us without notice.
NE_URL = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
          "v5.1.2/geojson/ne_50m_admin_0_countries.geojson")
NE_MIN_BYTES = 2 * 1024 * 1024      # v5.1.2 is 2.94 MB; well under that means truncated
TIMEOUT = 60
PLACEHOLDER = "__BUNDLE__"
B_PREFIX, B_SUFFIX = "const B = ", ";"      # the template's placeholder line


def fetch(path="ne50.geojson"):
    if os.path.exists(path):
        n = os.path.getsize(path)
        if n < NE_MIN_BYTES:
            raise SystemExit(f"{path} is only {n//1024} KB — truncated. "
                             f"Delete it and re-run fetch.")
        print(f"{path} already present ({n//1024} KB)")
        return
    print("downloading Natural Earth 1:50m country polygons…")
    tmp = path + ".part"            # same directory, so the os.replace below is atomic
    try:
        with urllib.request.urlopen(NE_URL, timeout=TIMEOUT) as r, open(tmp, "wb") as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
        n = os.path.getsize(tmp)
        if n < NE_MIN_BYTES:
            raise OSError(f"got {n//1024} KB, expected >{NE_MIN_BYTES//1024} KB")
    except BaseException as e:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise SystemExit(f"fetch failed: {e}\n  from {NE_URL}\n"
                         f"  partial download removed, {path} not written; re-run to retry") from e
    os.replace(tmp, path)
    print(f"wrote {path} ({os.path.getsize(path)//1024} KB)")


def build(script="build_data2.py"):
    print(f"running {script}…")
    subprocess.run([sys.executable, script], check=True)


def _escape(data):
    """Make a JSON blob safe to splice into a <script> element.

    A literal `</` would close the script early; `<` cannot appear outside a
    string in JSON, so the inserted backslash always lands inside one, where
    JSON reads `\\/` as `/`. U+2028/9 are bare characters to JSON but line
    terminators to a JavaScript parser.
    """
    return (data.replace("</", "<\\/")
                .replace("\u2028", "\\u2028")
                .replace("\u2029", "\\u2029"))


def _unescape(esc):
    return (esc.replace("\\u2029", "\u2029")
               .replace("\\u2028", "\u2028")
               .replace("<\\/", "</"))


def _render(template, data):
    tpl = open(template, encoding="utf-8").read()
    n = tpl.count(PLACEHOLDER)
    if n != 1:
        raise SystemExit(f"{template}: expected exactly one {PLACEHOLDER}, found {n}")
    esc = _escape(data)
    # _unescape is only injective if the bundle contains none of the escaped forms
    # already; json.dump never emits them, but refuse rather than ship a page that
    # extract would silently mis-invert.
    if _unescape(esc) != data:
        raise SystemExit("bundle text does not survive the <script> escaping — a literal "
                         "<\\/ or \\u2028 in the JSON would make extract ambiguous")
    return tpl.replace(PLACEHOLDER, esc)


def _spliced(html, page):
    """Pull the escaped bundle back off the `const B = …;` line."""
    for line in html.split("\n"):
        if line.startswith(B_PREFIX) and line.endswith(B_SUFFIX):
            return line[len(B_PREFIX):-len(B_SUFFIX)]
    raise SystemExit(f"{page}: no `{B_PREFIX}…{B_SUFFIX}` line to read the bundle from")


def inject(template="sim_template.html", bundle="bundle.json", out="../index.html"):
    html = _render(template, open(bundle, encoding="utf-8").read())
    open(out, "w", encoding="utf-8").write(html)
    print(f"wrote {out} ({os.path.getsize(out)//1024} KB)")


def extract(page="../index.html", bundle="bundle.json"):
    esc = _spliced(open(page, encoding="utf-8").read(), page)
    data = _unescape(esc)
    if _escape(data) != esc:            # extract has to invert inject exactly
        raise SystemExit(f"{page}: the spliced bundle does not round-trip through the escaping")
    json.loads(data)                    # cheap corruption check
    open(bundle, "w", encoding="utf-8").write(data)
    print(f"wrote {bundle} ({os.path.getsize(bundle)//1024} KB) from {page}")


def check(template="sim_template.html", bundle="bundle.json", page="../index.html"):
    have = open(page, "rb").read()
    src = bundle
    if os.path.exists(bundle):
        data = open(bundle, encoding="utf-8").read()
    else:
        # a fresh clone ships neither ne50.geojson nor bundle.json, so fall back to
        # the bundle already in the page — that still catches template drift
        data = _unescape(_spliced(have.decode("utf-8"), page))
        src = f"the bundle spliced into {page}"
    want = _render(template, data).encode("utf-8")
    if want == have:
        print(f"ok: {page} == {template} + {src} ({len(have)//1024} KB)")
        return
    m = min(len(want), len(have))
    i = next((k for k in range(m) if want[k] != have[k]), m)
    ln = want[:i].count(b"\n") + 1
    raise SystemExit(f"drift: {page} != {template} + {src}\n"
                     f"  first difference at line {ln}, byte {i} "
                     f"({len(have)} bytes on disk, {len(want)} rebuilt)\n"
                     f"  re-run `python3 build_site.py inject`, or mirror the edit into {template}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd not in ("fetch", "build", "inject", "extract", "check", "all"):
        raise SystemExit(__doc__)
    if cmd in ("fetch", "all"):
        fetch()
    if cmd in ("build", "all"):
        build()
    if cmd in ("inject", "all"):
        inject()
    if cmd == "extract":
        extract()
    if cmd == "check":
        check()
