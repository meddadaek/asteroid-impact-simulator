"""One-off asset preparation: land mask + city cache + NEO catalogue index.

Run once after cloning:  python app/build_assets.py
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import geo  # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))
TEXTURE = os.path.join(_HERE, "..", "..", "frontend", "textures",
                       "earth_specular.jpg")
CATALOG = os.path.join(geo.DATA_DIR, "neo_catalog.json")
CATALOG_OUT = os.path.join(geo.DATA_DIR, "neo_index.json")
SENTRY = os.path.join(geo.DATA_DIR, "sentry.json")


def build_neo_index(limit_featured: int = 400) -> dict:
    """Flatten the JPL catalogue into records the API can serve directly."""
    with open(CATALOG, "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    fields = raw["fields"]
    idx = {name: i for i, name in enumerate(fields)}

    records = []
    for row in raw["data"]:
        def get(key):
            v = row[idx[key]] if key in idx else None
            return v

        try:
            a = float(get("a")); e = float(get("e")); i = float(get("i"))
            om = float(get("om")); w = float(get("w")); ma = float(get("ma"))
            epoch = float(get("epoch"))
        except (TypeError, ValueError):
            continue
        if not (0.05 < a < 60 and 0.0 <= e < 0.999):
            continue

        H = get("H")
        diameter = get("diameter")
        albedo = get("albedo")
        try:
            H = float(H) if H is not None else None
        except ValueError:
            H = None
        try:
            diameter_km = float(diameter) if diameter is not None else None
        except ValueError:
            diameter_km = None
        if diameter_km is None and H is not None:
            # standard H -> diameter relation with an assumed albedo
            p = 0.14
            try:
                p = float(albedo) if albedo else 0.14
            except ValueError:
                p = 0.14
            p = min(max(p, 0.02), 0.6)
            diameter_km = 1329.0 / np.sqrt(p) * 10 ** (-0.2 * H) / 1000.0

        try:
            moid = float(get("moid")) if get("moid") is not None else None
        except ValueError:
            moid = None

        records.append({
            "name": (get("full_name") or "").strip(),
            "a": a, "e": e, "i": i, "om": om, "w": w, "ma": ma, "epoch": epoch,
            "H": H,
            "diameter_m": round(diameter_km * 1000.0, 1) if diameter_km else None,
            "moid_au": moid,
            "class": get("class"),
            "pha": get("pha") == "Y",
        })

    # Featured set: potentially hazardous, closest MOID, biggest first.
    hazardous = [r for r in records if r["pha"] and r["moid_au"] is not None]
    hazardous.sort(key=lambda r: (r["moid_au"], -(r["diameter_m"] or 0)))
    featured = hazardous[:limit_featured]

    # Always include the household names if the catalogue has them.
    wanted = ["Apophis", "Bennu", "Didymos", "Eros", "Itokawa", "Ryugu",
              "Toutatis", "Phaethon", "Icarus", "Geographos", "Nereus"]
    by_name = {}
    for r in records:
        for w_ in wanted:
            if w_.lower() in r["name"].lower() and w_ not in by_name:
                by_name[w_] = r
    for r in by_name.values():
        if r not in featured:
            featured.insert(0, r)

    sentry_rows = []
    if os.path.exists(SENTRY):
        with open(SENTRY, "r", encoding="utf-8") as fh:
            s = json.load(fh)
        for row in s.get("data", []):
            try:
                sentry_rows.append({
                    "designation": row.get("des"),
                    "name": row.get("fullname", "").strip(),
                    "impact_probability": float(row.get("ip", 0) or 0),
                    "diameter_km": float(row.get("diameter") or 0),
                    "v_inf_kms": float(row.get("v_inf") or 0),
                    "palermo_scale": float(row.get("ps_cum") or 0),
                    "torino_scale": int(float(row.get("ts_max") or 0)),
                    "year_range": row.get("range"),
                    "n_impacts": int(row.get("n_imp") or 0),
                })
            except (TypeError, ValueError):
                continue
    sentry_rows.sort(key=lambda r: -r["palermo_scale"])

    out = {"total": len(records), "featured": featured,
           "sentry": sentry_rows[:200]}
    with open(CATALOG_OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh)
    return {"catalog_records": len(records), "featured": len(featured),
            "sentry": len(sentry_rows)}


def main():
    print("Building land mask from NASA specular texture...")
    mask = geo.build_land_mask(TEXTURE)
    frac = mask.mean()
    print(f"  {mask.shape[1]}x{mask.shape[0]} grid, land fraction {frac:.1%} "
          f"(true value ~29%)")

    print("Building city cache from GeoNames...")
    info = geo.build_city_cache()
    print(f"  {info['count']} cities, {info['total_pop']/1e9:.2f} bn people")

    print("Indexing the JPL NEO catalogue...")
    stats = build_neo_index()
    print(f"  {stats['catalog_records']} usable orbits, "
          f"{stats['featured']} featured, {stats['sentry']} Sentry objects")

    # spot checks
    print("\nSpot checks:")
    for name, lat, lon, expect in [
        ("Sahara",        23.0,  13.0, "land"),
        ("Pacific",        0.0, -140.0, "water"),
        ("Amazon",        -3.0, -60.0, "land"),
        ("Mid-Atlantic",  30.0, -40.0, "water"),
        ("Siberia",       62.0,  95.0, "land"),
        ("Algiers",       36.75,  3.06, "land"),
    ]:
        got = "land" if geo.is_land(lat, lon) else "water"
        flag = "ok " if got == expect else "BAD"
        print(f"  [{flag}] {name:14s} -> {got}")


if __name__ == "__main__":
    main()
