"""Download the source data and imagery the app is built on.

Run once after cloning (``run.ps1 -Setup`` / ``run.sh --setup`` do it for you):

    python app/fetch_data.py

Every source is free and needs no account, key, or payment method:

* JPL Small-Body Database Query API  -- orbital elements for every known NEO
* NASA CNEOS Sentry                  -- objects with a non-zero impact risk
* GeoNames cities15000               -- cities over 15 000 people (CC BY 4.0)
* NASA Visible Earth / Three.js      -- globe imagery (public domain / MIT)

Files already present are left alone unless ``--force`` is passed.
"""
from __future__ import annotations

import argparse
import io
import os
import sys
import urllib.request
import zipfile

_HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.abspath(os.path.join(_HERE, "..", "data"))
TEX = os.path.abspath(os.path.join(_HERE, "..", "..", "frontend", "textures"))
VENDOR = os.path.abspath(os.path.join(_HERE, "..", "..", "frontend", "vendor"))

SBDB = ("https://ssd-api.jpl.nasa.gov/sbdb_query.api"
        "?fields=full_name,a,e,i,om,w,ma,epoch,H,diameter,albedo,moid,class,pha,n,per"
        "&sb-group=neo&sb-kind=a")
SENTRY = "https://ssd-api.jpl.nasa.gov/sentry.api"
CITIES = "http://download.geonames.org/export/dump/cities15000.zip"

THREE = "https://unpkg.com/three@0.160.0"

DATASETS = [
    (SBDB, os.path.join(DATA, "neo_catalog.json")),
    (SENTRY, os.path.join(DATA, "sentry.json")),
]

TEXTURES = [
    ("https://eoimages.gsfc.nasa.gov/images/imagerecords/73000/73909/"
     "world.topo.bathy.200412.3x5400x2700.jpg", "earth_day.jpg"),
    ("https://eoimages.gsfc.nasa.gov/images/imagerecords/55000/55167/"
     "earth_lights_lrg.jpg", "earth_night.jpg"),
    ("https://eoimages.gsfc.nasa.gov/images/imagerecords/57000/57747/"
     "cloud_combined_2048.jpg", "earth_clouds.jpg"),
    (f"{THREE}/examples/textures/planets/earth_specular_2048.jpg",
     "earth_specular.jpg"),
    (f"{THREE}/examples/textures/planets/earth_normal_2048.jpg",
     "earth_normal.jpg"),
    (f"{THREE}/examples/textures/planets/moon_1024.jpg", "moon.jpg"),
]

VENDOR_FILES = [
    (f"{THREE}/build/three.module.js", "three.module.js"),
    (f"{THREE}/examples/jsm/controls/OrbitControls.js", "controls/OrbitControls.js"),
    (f"{THREE}/examples/jsm/postprocessing/EffectComposer.js", "postprocessing/EffectComposer.js"),
    (f"{THREE}/examples/jsm/postprocessing/RenderPass.js", "postprocessing/RenderPass.js"),
    (f"{THREE}/examples/jsm/postprocessing/ShaderPass.js", "postprocessing/ShaderPass.js"),
    (f"{THREE}/examples/jsm/postprocessing/MaskPass.js", "postprocessing/MaskPass.js"),
    (f"{THREE}/examples/jsm/postprocessing/UnrealBloomPass.js", "postprocessing/UnrealBloomPass.js"),
    (f"{THREE}/examples/jsm/postprocessing/OutputPass.js", "postprocessing/OutputPass.js"),
    (f"{THREE}/examples/jsm/postprocessing/Pass.js", "postprocessing/Pass.js"),
    (f"{THREE}/examples/jsm/shaders/CopyShader.js", "shaders/CopyShader.js"),
    (f"{THREE}/examples/jsm/shaders/LuminosityHighPassShader.js", "shaders/LuminosityHighPassShader.js"),
    (f"{THREE}/examples/jsm/shaders/OutputShader.js", "shaders/OutputShader.js"),
]

UA = {"User-Agent": "orbital-sentinel/1.0 (+https://github.com)"}


def _get(url: str, timeout: int = 300) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def download(url: str, dest: str, force: bool = False) -> bool:
    if os.path.exists(dest) and not force and os.path.getsize(dest) > 0:
        print(f"  have  {os.path.basename(dest)}")
        return False
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    print(f"  get   {os.path.basename(dest)} ...", end="", flush=True)
    data = _get(url)
    with open(dest, "wb") as fh:
        fh.write(data)
    print(f" {len(data)/1e6:.1f} MB")
    return True


def fetch_cities(force: bool = False):
    txt = os.path.join(DATA, "cities15000.txt")
    if os.path.exists(txt) and not force:
        print("  have  cities15000.txt")
        return
    os.makedirs(DATA, exist_ok=True)
    print("  get   cities15000.zip ...", end="", flush=True)
    blob = _get(CITIES)
    print(f" {len(blob)/1e6:.1f} MB")
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        z.extract("cities15000.txt", DATA)
    print("  unzip cities15000.txt")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="re-download everything")
    args = ap.parse_args()

    print("Catalogues (JPL SSD / CNEOS):")
    for url, dest in DATASETS:
        download(url, dest, args.force)

    print("Cities (GeoNames):")
    fetch_cities(args.force)

    print("Imagery (NASA Visible Earth):")
    for url, name in TEXTURES:
        download(url, os.path.join(TEX, name), args.force)

    print("Three.js runtime:")
    for url, name in VENDOR_FILES:
        download(url, os.path.join(VENDOR, name), args.force)

    print("\nDone. Next: python app/build_assets.py")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:                       # noqa: BLE001
        print(f"\nfailed: {exc}", file=sys.stderr)
        sys.exit(1)
