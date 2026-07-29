"""Companion helper: the two steps I originally ran inline rather than from a file.

    python3 build_site.py fetch     # download the Natural Earth coastlines
    python3 build_data2.py          # -> bundle.json
    python3 build_site.py inject    # bundle.json + template -> final HTML
"""
import os
import sys
import urllib.request

NE_URL = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
          "master/geojson/ne_50m_admin_0_countries.geojson")


def fetch(path="ne50.geojson"):
    if os.path.exists(path):
        print(f"{path} already present")
        return
    print("downloading Natural Earth 1:50m country polygons…")
    urllib.request.urlretrieve(NE_URL, path)
    print(f"wrote {path} ({os.path.getsize(path)//1024} KB)")


def inject(template="sim_template.html", bundle="bundle.json",
           out="openeclipse-simulator.html"):
    tpl = open(template, encoding="utf-8").read()
    data = open(bundle, encoding="utf-8").read()
    if "__BUNDLE__" not in tpl:
        raise SystemExit(f"{template} has no __BUNDLE__ placeholder")
    open(out, "w", encoding="utf-8").write(tpl.replace("__BUNDLE__", data))
    print(f"wrote {out} ({os.path.getsize(out)//1024} KB)")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd in ("fetch", "all"):
        fetch()
    if cmd in ("inject", "all"):
        inject()
