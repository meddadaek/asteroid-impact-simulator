"""Orbital Sentinel -- FastAPI service and static host for the 3D client.

Run from the repository root:

    backend/.venv/Scripts/python -m uvicorn app.main:app --app-dir backend/app --reload

or just use ``run.ps1`` / ``run.sh``.
"""
from __future__ import annotations

import json
import math
import os
import time

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import dataset
import geo
import impact as impact_mod
import predict
from constants import IMPACTOR_TYPES, REFERENCE_EVENTS
from orbital import Elements
from schemas import EffectsRequest, ElementsRequest, SimpleRequest

_HERE = os.path.dirname(os.path.abspath(__file__))
FRONTEND = os.path.abspath(os.path.join(_HERE, "..", "..", "frontend"))
DATA_DIR = os.path.abspath(os.path.join(_HERE, "..", "data"))
MODEL_DIR = os.path.abspath(os.path.join(_HERE, "..", "models"))

app = FastAPI(title="Orbital Sentinel",
              description="Near-Earth object impact prediction and consequence "
                          "modelling",
              version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])


def _density_for(spec) -> float:
    if getattr(spec, "density_kgm3", None):
        return float(spec.density_kgm3)
    return float(IMPACTOR_TYPES[spec.material]["density"])


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "models_loaded": predict.models_available(),
        "base_epoch_jd": dataset.JD_BASE,
        "materials": {k: v for k, v in IMPACTOR_TYPES.items()},
        "uncertainty_presets": predict.UNCERTAINTY_PRESETS,
        "reference_events": REFERENCE_EVENTS,
    }


@app.get("/api/models")
def model_report():
    path = os.path.join(MODEL_DIR, "training_report.json")
    if not os.path.exists(path):
        raise HTTPException(404, "no training report; run app/train.py first")
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------
_neo_cache = {}


def _neo_index():
    if "data" not in _neo_cache:
        path = os.path.join(DATA_DIR, "neo_index.json")
        with open(path, "r", encoding="utf-8") as fh:
            _neo_cache["data"] = json.load(fh)
    return _neo_cache["data"]


@app.get("/api/neos")
def list_neos(search: str = Query("", max_length=64),
              limit: int = Query(60, ge=1, le=400)):
    """Real near-Earth objects from the JPL Small-Body Database."""
    idx = _neo_index()
    rows = idx["featured"]
    if search:
        s = search.lower()
        rows = [r for r in rows if s in r["name"].lower()]
    return {"total_catalogue": idx["total"], "count": len(rows[:limit]),
            "objects": rows[:limit]}


@app.get("/api/sentry")
def sentry(limit: int = Query(40, ge=1, le=200)):
    """NASA CNEOS Sentry list: objects with a non-zero computed impact risk."""
    idx = _neo_index()
    return {"objects": idx.get("sentry", [])[:limit]}


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------
@app.post("/api/effects")
def effects(req: EffectsRequest):
    """Damage profile for a stated impactor. The fast path used by the sliders."""
    t0 = time.time()
    density = _density_for(req)
    v = req.velocity_kms * 1000.0

    analytic = impact_mod.impact_effects(req.diameter_m, density, v,
                                         req.angle_deg, req.target)
    t_phys = time.time() - t0

    ml = {}
    t_ml = 0.0
    if req.use_surrogate and predict.models_available():
        t1 = time.time()
        ml = predict.predict_effects_ml(req.diameter_m, density, v,
                                        req.angle_deg, req.target)
        t_ml = time.time() - t1

    return {
        "physics": analytic,
        "surrogate": ml,
        "comparison": predict.compare_effects(analytic, ml),
        "timing_ms": {"physics": round(t_phys * 1000, 3),
                      "surrogate": round(t_ml * 1000, 3)},
    }


@app.post("/api/simulate/simple")
def simulate_simple(req: SimpleRequest):
    """Simple mode: impactor and impact point stated directly."""
    density = _density_for(req)
    return predict.resolve_impact(
        req.latitude, req.longitude, req.diameter_m, density,
        req.velocity_kms * 1000.0, req.angle_deg,
        azimuth_deg=req.azimuth_deg, jd=dataset.JD_BASE, hypothetical=False)


@app.post("/api/simulate/elements")
def simulate_elements(req: ElementsRequest):
    """Astronomer mode: propagate a real orbit and resolve any encounter."""
    el = Elements(a=req.a, e=req.e, i=req.i, om=req.om, w=req.w, ma=req.ma,
                  epoch=req.epoch if req.epoch else dataset.JD_BASE)
    density = _density_for(req)
    t0 = time.time()
    out = predict.simulate_from_elements(
        el, req.diameter_m, density, uncertainty=req.uncertainty,
        n_clones=req.n_clones, years=req.horizon_years,
        force_impact=req.force_impact)
    out["timing_ms"] = {"total": round((time.time() - t0) * 1000, 1)}
    return out


@app.get("/api/geo/terrain")
def terrain(lat: float = Query(..., ge=-90, le=90),
            lon: float = Query(..., ge=-180, le=180)):
    return {"latitude": lat, "longitude": lon,
            "on_land": geo.is_land(lat, lon),
            "terrain": geo.terrain_at(lat, lon),
            "nearest_cities": geo.nearest_cities(lat, lon, 5)}


# ---------------------------------------------------------------------------
# Static client
# ---------------------------------------------------------------------------
if os.path.isdir(FRONTEND):
    app.mount("/textures", StaticFiles(directory=os.path.join(FRONTEND, "textures")),
              name="textures")
    app.mount("/vendor", StaticFiles(directory=os.path.join(FRONTEND, "vendor")),
              name="vendor")
    app.mount("/js", StaticFiles(directory=os.path.join(FRONTEND, "js")),
              name="js")
    app.mount("/css", StaticFiles(directory=os.path.join(FRONTEND, "css")),
              name="css")

    @app.get("/")
    def index():
        return FileResponse(os.path.join(FRONTEND, "index.html"))
