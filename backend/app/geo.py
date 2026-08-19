"""Geography: land/ocean classification and population exposure.

Two bundled datasets, both public-domain / permissively licensed and shipped
with the repo so the app has no runtime network dependency:

* a land-ocean mask rasterised from the NASA specular map (ocean is bright,
  land is dark in that texture), collapsed to a 1440x720 boolean grid;
* GeoNames ``cities15000`` -- every city over 15 000 people, with coordinates
  and population, used to estimate how many people fall inside each damage ring.
"""
from __future__ import annotations

import csv
import math
import os
from functools import lru_cache

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(_HERE, "..", "data")
MASK_PATH = os.path.join(DATA_DIR, "land_mask.npy")
CITIES_PATH = os.path.join(DATA_DIR, "cities15000.txt")
CITIES_NPZ = os.path.join(DATA_DIR, "cities.npz")

EARTH_RADIUS_KM = 6371.0


# ---------------------------------------------------------------------------
# Land / ocean
# ---------------------------------------------------------------------------
def build_land_mask(texture_path: str, width: int = 1440, height: int = 720,
                    threshold: int = 90) -> np.ndarray:
    """Rasterise the specular texture into a boolean land mask and cache it.

    In the NASA specular map the oceans are bright (they reflect) and the land
    is close to black, so a simple luminance threshold separates them cleanly.
    """
    from PIL import Image

    img = Image.open(texture_path).convert("L").resize((width, height),
                                                       Image.BILINEAR)
    arr = np.asarray(img, dtype=np.uint8)
    land = arr < threshold
    np.save(MASK_PATH, land)
    return land


@lru_cache(maxsize=1)
def land_mask() -> np.ndarray:
    if not os.path.exists(MASK_PATH):
        raise FileNotFoundError(
            "land_mask.npy missing -- run build_assets.py to generate it")
    return np.load(MASK_PATH)


def is_land(lat: float, lon: float) -> bool:
    """True if the given coordinate falls on land."""
    mask = land_mask()
    h, w = mask.shape
    row = int((90.0 - lat) / 180.0 * h)
    col = int((lon + 180.0) / 360.0 * w)
    row = max(0, min(h - 1, row))
    col = max(0, min(w - 1, col))
    return bool(mask[row, col])


def terrain_at(lat: float, lon: float) -> str:
    """Target type for the impact physics: 'water' or 'sedimentary'."""
    return "sedimentary" if is_land(lat, lon) else "water"


# ---------------------------------------------------------------------------
# Cities and population exposure
# ---------------------------------------------------------------------------
def build_city_cache() -> dict:
    """Parse the GeoNames dump into a compact npz of lat/lon/pop/name."""
    lats, lons, pops, names, countries = [], [], [], [], []
    with open(CITIES_PATH, "r", encoding="utf-8") as fh:
        for row in csv.reader(fh, delimiter="\t", quoting=csv.QUOTE_NONE):
            if len(row) < 15:
                continue
            try:
                pop = int(row[14])
            except ValueError:
                continue
            if pop <= 0:
                continue
            lats.append(float(row[4]))
            lons.append(float(row[5]))
            pops.append(pop)
            names.append(row[1])
            countries.append(row[8])
    np.savez_compressed(CITIES_NPZ,
                        lat=np.array(lats, dtype=np.float32),
                        lon=np.array(lons, dtype=np.float32),
                        pop=np.array(pops, dtype=np.int64),
                        name=np.array(names, dtype=object),
                        country=np.array(countries, dtype=object))
    return {"count": len(lats), "total_pop": int(sum(pops))}


@lru_cache(maxsize=1)
def cities():
    if not os.path.exists(CITIES_NPZ):
        raise FileNotFoundError(
            "cities.npz missing -- run build_assets.py to generate it")
    d = np.load(CITIES_NPZ, allow_pickle=True)
    return (d["lat"].astype(np.float64), d["lon"].astype(np.float64),
            d["pop"], d["name"], d["country"])


def great_circle_km(lat0: float, lon0: float, lats, lons):
    """Haversine distance from one point to arrays of points, in km."""
    p0 = math.radians(lat0)
    p1 = np.radians(lats)
    dphi = p1 - p0
    dlam = np.radians(lons - lon0)
    a = (np.sin(dphi / 2) ** 2
         + math.cos(p0) * np.cos(p1) * np.sin(dlam / 2) ** 2)
    return 2.0 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def nearest_cities(lat: float, lon: float, n: int = 6) -> list:
    clat, clon, cpop, cname, ccountry = cities()
    d = great_circle_km(lat, lon, clat, clon)
    idx = np.argsort(d)[:n]
    return [{"name": str(cname[i]), "country": str(ccountry[i]),
             "population": int(cpop[i]), "distance_km": round(float(d[i]), 1),
             "lat": float(clat[i]), "lon": float(clon[i])}
            for i in idx]


def population_within(lat: float, lon: float, radius_km: float) -> int:
    """Total city population inside a radius. Undercounts rural population."""
    if radius_km <= 0:
        return 0
    clat, clon, cpop, _, _ = cities()
    d = great_circle_km(lat, lon, clat, clon)
    return int(cpop[d <= radius_km].sum())


def cities_within(lat: float, lon: float, radius_km: float,
                  limit: int = 40) -> list:
    if radius_km <= 0:
        return []
    clat, clon, cpop, cname, ccountry = cities()
    d = great_circle_km(lat, lon, clat, clon)
    sel = np.where(d <= radius_km)[0]
    sel = sel[np.argsort(-cpop[sel])][:limit]
    return [{"name": str(cname[i]), "country": str(ccountry[i]),
             "population": int(cpop[i]), "distance_km": round(float(d[i]), 1),
             "lat": float(clat[i]), "lon": float(clon[i])}
            for i in sel]


# ---------------------------------------------------------------------------
# Damage-ring exposure report
# ---------------------------------------------------------------------------
# Each ring: (path in the effects dict, stable id, English label, colour).
# The id is what the client translates against, so adding a language never
# needs the wording here to change.
DAMAGE_RINGS = [
    ("blast.total_destruction_km",  "total_destruction",  "Total destruction",         "#ff2d1a"),
    ("blast.concrete_buildings_km", "concrete_fails",     "Reinforced buildings fail", "#ff6a1a"),
    ("blast.homes_collapse_km",     "homes_collapse",     "Houses collapse",           "#ff9f1a"),
    ("thermal.burns_3rd_degree_km", "burns_3rd",          "Third-degree burns",        "#ffd21a"),
    ("blast.trees_blown_down_km",   "trees_flattened",    "Trees flattened",           "#c8e34a"),
    ("blast.windows_shatter_km",    "windows_shatter",    "Windows shatter",           "#5ad1e6"),
]


def _dig(d: dict, dotted: str):
    cur = d
    for part in dotted.split("."):
        if cur is None:
            return 0.0
        cur = cur.get(part)
    return float(cur or 0.0)


def exposure_report(lat: float, lon: float, effects: dict) -> dict:
    """Turn the physical damage radii into a human-consequence summary."""
    rings = []
    seen_pop = 0
    for key, ring_id, label, colour in DAMAGE_RINGS:
        radius = _dig(effects, key)
        if radius <= 0:
            continue
        pop = population_within(lat, lon, radius)
        rings.append({
            "id": ring_id,
            "label": label,
            "radius_km": round(radius, 2),
            "colour": colour,
            "population": pop,
            "incremental_population": max(0, pop - seen_pop),
            "area_km2": round(math.pi * radius ** 2, 1),
        })
        seen_pop = max(seen_pop, pop)

    largest = max((r["radius_km"] for r in rings), default=0.0)
    return {
        "on_land": is_land(lat, lon),
        "terrain": terrain_at(lat, lon),
        "rings": rings,
        "nearest_cities": nearest_cities(lat, lon, 6),
        "affected_cities": cities_within(lat, lon, largest, 25),
        "total_population_affected": seen_pop,
    }
