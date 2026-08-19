"""Inference layer: ML surrogates plus the exact physics, side by side.

The app deliberately reports both for every query.

* The **surrogate** answers in microseconds. That is what makes the globe
  respond to a slider drag at 60 fps.
* The **analytic** solution is the ground truth the surrogate was fitted to.
  Showing both makes the model's error visible instead of hiding it.

For impact probability specifically there are two different questions:

* the classifier gives a *risk score* over the training population, which is a
  screening tool, and
* :func:`monte_carlo_probability` gives the honest impact probability for one
  specific orbit under a stated observational uncertainty, by propagating a
  cloud of clones. That costs a second or two, which is affordable for the one
  orbit the user actually asked about.
"""
from __future__ import annotations

import math
import os
from functools import lru_cache

import joblib
import numpy as np

import dataset
import geo
import impact as impact_mod
import orbital
from constants import AU, DAY, J_PER_MEGATON
from orbital import Elements

_HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(_HERE, "..", "models")


# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _models():
    def load(name):
        path = os.path.join(MODEL_DIR, name)
        return joblib.load(path) if os.path.exists(path) else None

    return {
        "orbit_clf": load("orbit_impact_clf.pkl"),
        "orbit_dist": load("orbit_distance_reg.pkl"),
        "effects_clf": load("effects_airburst_clf.pkl"),
        "effects_reg": load("effects_reg.pkl"),
    }


def models_available() -> bool:
    m = _models()
    return all(m[k] is not None for k in
               ("orbit_clf", "effects_clf", "effects_reg"))


# ---------------------------------------------------------------------------
# Effects: surrogate vs analytic
# ---------------------------------------------------------------------------
def _effect_features(diameter, density, velocity, angle, target_density):
    mass = density * math.pi / 6.0 * diameter ** 3
    e_init_mt = 0.5 * mass * velocity ** 2 / J_PER_MEGATON
    return np.array([[math.log10(diameter), density, velocity / 1000.0, angle,
                      math.log10(max(mass, 1e-9)),
                      math.log10(max(e_init_mt, 1e-30)), target_density]])


def predict_effects_ml(diameter, density, velocity, angle,
                       target: str = "sedimentary") -> dict:
    """Surrogate prediction of the damage profile."""
    m = _models()
    if m["effects_reg"] is None:
        return {}
    rho_t = impact_mod.TARGETS.get(target, impact_mod.RHO_TARGET_SED)
    X = _effect_features(diameter, density, velocity, angle, rho_t)

    p_airburst = float(m["effects_clf"].predict_proba(X)[0, 1])
    bundle = m["effects_reg"]
    out = {}
    for name, reg in bundle["models"].items():
        out[name] = float(reg.predict(X)[0])

    def unlog(key, floor=0.0):
        v = 10.0 ** out[key]
        return 0.0 if v <= floor else v

    # Gate the two conditional targets on the classifier's verdict: an airburst
    # has a burst altitude and no crater, a ground impact the reverse. Each
    # regressor was only fitted where its quantity is defined, so reading it on
    # the wrong side of the boundary is meaningless.
    airburst = p_airburst >= 0.5

    return {
        "airburst_probability": p_airburst,
        "airburst": airburst,
        "energy_deposited_mt": unlog("log_energy_deposited_mt"),
        "burst_altitude_km": max(0.0, out["burst_altitude_km"]) if airburst else 0.0,
        "crater_diameter_m": 0.0 if airburst else unlog("log_crater_diameter_m", 1.0),
        "blast_20kpa_km": unlog("log_blast_20kpa_km", 1e-3),
        "blast_4kpa_km": unlog("log_blast_4kpa_km", 1e-3),
        "blast_1kpa_km": unlog("log_blast_1kpa_km", 1e-3),
        "thermal_3rd_km": unlog("log_thermal_3rd_km", 1e-3),
        "seismic_magnitude": out["seismic_magnitude"],
    }


def compare_effects(analytic: dict, ml: dict) -> list:
    """Line-by-line surrogate-vs-physics table for the UI."""
    if not ml:
        return []
    # (stable id, English label, unit, analytic value, surrogate value)
    pairs = [
        ("energyReleased", "Energy released", "Mt",
         analytic["energy_deposited_mt"], ml["energy_deposited_mt"]),
        ("burstAltitude", "Burst altitude", "km",
         analytic["burst_altitude_km"], ml["burst_altitude_km"]),
        ("craterDiameter", "Crater diameter", "m",
         (analytic["crater"] or {}).get("final_diameter_m", 0.0),
         ml["crater_diameter_m"]),
        ("homesCollapse", "Houses collapse", "km",
         analytic["blast"]["homes_collapse_km"], ml["blast_20kpa_km"]),
        ("treesFlattened", "Trees flattened", "km",
         analytic["blast"]["trees_blown_down_km"], ml["blast_4kpa_km"]),
        ("windowsShatter", "Windows shatter", "km",
         analytic["blast"]["windows_shatter_km"], ml["blast_1kpa_km"]),
        ("burns3rd", "Third-degree burns", "km",
         analytic["thermal"]["burns_3rd_degree_km"], ml["thermal_3rd_km"]),
        ("seismicMagnitude", "Seismic magnitude", "M",
         analytic["seismic"]["magnitude"], ml["seismic_magnitude"]),
    ]
    rows = []
    for key, label, unit, a, b in pairs:
        a = float(a or 0.0)
        b = float(b or 0.0)
        err = abs(b - a) / a * 100.0 if a > 1e-9 else (0.0 if b < 1e-9 else 100.0)
        rows.append({"id": key, "label": label, "unit": unit,
                     "physics": round(a, 4), "surrogate": round(b, 4),
                     "error_pct": round(err, 2)})
    return rows


# ---------------------------------------------------------------------------
# Orbit risk
# ---------------------------------------------------------------------------
def predict_orbit_risk(el: Elements) -> dict:
    """Instant ML risk score for one orbit."""
    m = _models()
    if m["orbit_clf"] is None:
        return {}
    X = dataset.orbit_features(
        np.array([el.a]), np.array([el.e]), np.array([el.i]),
        np.array([el.om]), np.array([el.w]), np.array([el.ma]))
    p = float(m["orbit_clf"].predict_proba(X)[0, 1])
    out = {"ml_risk_score": p, "moid_au": float(X[0, 18])}
    if m["orbit_dist"] is not None:
        out["ml_predicted_min_distance_au"] = float(
            10.0 ** m["orbit_dist"].predict(X)[0])
    return out


# Observational uncertainty presets. Real 1-sigma element errors for a
# well-observed NEO are far smaller than the "poorly observed" row; the point of
# the spread is to let the user see how quickly an impact prediction degrades.
UNCERTAINTY_PRESETS = {
    "precise":  {"a": 1e-7, "e": 1e-7, "i": 1e-5, "angles": 1e-5,
                 "label": "Decades of radar tracking"},
    "good":     {"a": 1e-6, "e": 1e-6, "i": 1e-4, "angles": 1e-4,
                 "label": "Well observed, multi-apparition"},
    "moderate": {"a": 1e-5, "e": 1e-5, "i": 1e-3, "angles": 1e-3,
                 "label": "Several months of observation"},
    "poor":     {"a": 1e-4, "e": 1e-4, "i": 1e-2, "angles": 1e-2,
                 "label": "Newly discovered, short arc"},
}


def monte_carlo_probability(el: Elements, uncertainty: str = "moderate",
                            n_clones: int = 3000, years: float = 30.0,
                            seed: int = 0) -> dict:
    """Honest impact probability for one orbit under stated uncertainty.

    Generates a cloud of clones consistent with the quoted 1-sigma element
    errors, propagates all of them, and counts how many are captured by Earth.
    This is the calculation the ML classifier is a fast approximation of.
    """
    cfg = UNCERTAINTY_PRESETS.get(uncertainty, UNCERTAINTY_PRESETS["moderate"])
    rng = np.random.default_rng(seed)
    n = n_clones

    clones = {
        "a": el.a * (1.0 + rng.normal(0, cfg["a"], n)),
        "e": np.clip(el.e + rng.normal(0, cfg["e"], n), 0.0, 0.9999),
        "i": el.i + rng.normal(0, cfg["i"], n),
        "om": el.om + rng.normal(0, cfg["angles"], n),
        "w": el.w + rng.normal(0, cfg["angles"], n),
        "ma": el.ma + rng.normal(0, cfg["angles"], n),
        "epoch": np.full(n, el.epoch),
    }
    # Search only around the nominal orbit's own encounters. The half-width is
    # set by how far the perturbations can drag an encounter along-track: a
    # fractional error in the semi-major axis feeds straight into the period, so
    # the timing slips by roughly (3/2)(da/a) x horizon, plus a healthy margin.
    approaches = orbital.find_close_approaches(el, el.epoch, years=years,
                                               max_results=24)
    if approaches:
        drift = 1.5 * cfg["a"] * years * 365.25
        half_width = float(min(max(4.0 * drift, 3.0), 60.0))
        d_min, jd_min, v_inf = orbital.batch_closest_approach_windows(
            clones, [c.jd for c in approaches], half_width, step_days=0.25)
    else:
        d_min, jd_min, v_inf = orbital.batch_closest_approach(
            clones, el.epoch, years=years, step_days=1.0)
    b_crit = orbital.capture_radius(v_inf) / AU
    hits = d_min < b_crit
    k = int(hits.sum())

    # Wilson score interval, which stays sensible when k is 0
    z = 1.96
    phat = k / n
    denom = 1 + z ** 2 / n
    centre = (phat + z ** 2 / (2 * n)) / denom
    half = z * math.sqrt(phat * (1 - phat) / n + z ** 2 / (4 * n ** 2)) / denom

    return {
        "uncertainty": uncertainty,
        "uncertainty_label": cfg["label"],
        "n_clones": n,
        "n_impacts": k,
        "probability": phat,
        "ci_low": max(0.0, centre - half),
        "ci_high": min(1.0, centre + half),
        "horizon_years": years,
        "median_min_distance_au": float(np.median(d_min)),
        "closest_clone_km": float(d_min.min() * AU / 1000.0),
        "median_v_inf_kms": float(np.median(v_inf)) / 1000.0,
        "impact_epochs_jd": [float(x) for x in jd_min[hits][:50]],
    }


# ---------------------------------------------------------------------------
# The full scenario
# ---------------------------------------------------------------------------
def simulate_from_elements(el: Elements, diameter: float, density: float,
                           uncertainty: str = "moderate",
                           n_clones: int = 3000, years: float = 30.0,
                           force_impact: bool = False) -> dict:
    """Astronomer mode: propagate a real orbit, then resolve the consequences.

    ``force_impact`` answers the question the app exists to ask -- "what if it
    did hit?" -- by taking the geometry of the closest approach and shrinking the
    impact parameter until the body is captured, leaving the encounter velocity
    and direction physically correct.
    """
    approaches = orbital.find_close_approaches(el, el.epoch, years=years,
                                               max_results=8)
    risk = predict_orbit_risk(el)
    mc = monte_carlo_probability(el, uncertainty, n_clones, years)

    result = {
        "elements": el.as_dict(),
        "orbit": {
            "perihelion_au": el.perihelion(),
            "aphelion_au": el.aphelion(),
            "period_days": el.period_days(),
            "period_years": el.period_days() / 365.25,
        },
        "risk": risk,
        "monte_carlo": mc,
        "close_approaches": [
            {"jd": c.jd, "distance_au": c.distance_au,
             "distance_km": c.distance_km,
             "distance_lunar": c.distance_km / 384400.0,
             "v_inf_kms": c.v_inf_kms, "v_impact_kms": c.v_impact_kms,
             "impact": c.impact}
            for c in approaches
        ],
        "orbit_path": orbital.sample_orbit_path(el, el.epoch, 400),
        "earth_path": _earth_path(el.epoch),
        "impact": None,
    }

    if not approaches:
        return result

    ca = approaches[0]
    if ca.impact or force_impact:
        geom = orbital.solve_impact_point(
            ca, b_offset_km=(None if ca.impact else ca.b_crit_km * 0.35))
        if geom is not None:
            result["impact"] = resolve_impact(
                geom.latitude, geom.longitude, diameter, density,
                geom.v_impact_kms * 1000.0, geom.entry_angle_deg,
                azimuth_deg=geom.azimuth_deg, jd=geom.jd,
                hypothetical=not ca.impact)
    return result


def _earth_path(jd0: float, n: int = 365) -> list:
    jd = np.linspace(jd0, jd0 + 365.25, n)
    r = orbital.batch_earth_positions(jd)
    return [[float(p[0]), float(p[1]), float(p[2])] for p in r]


def resolve_impact(lat: float, lon: float, diameter: float, density: float,
                   velocity: float, angle: float,
                   azimuth_deg: float = 0.0, jd: float | None = None,
                   hypothetical: bool = False) -> dict:
    """Everything that happens once a location and impactor are known."""
    target = geo.terrain_at(lat, lon)
    analytic = impact_mod.impact_effects(diameter, density, velocity, angle,
                                         target)
    ml = predict_effects_ml(diameter, density, velocity, angle, target)
    exposure = geo.exposure_report(lat, lon, analytic)

    return {
        "hypothetical": hypothetical,
        "location": {"latitude": lat, "longitude": lon,
                     "azimuth_deg": azimuth_deg, "jd": jd,
                     "terrain": target, "on_land": exposure["on_land"]},
        "impactor": {"diameter_m": diameter, "density_kgm3": density,
                     "velocity_kms": velocity / 1000.0, "angle_deg": angle},
        "physics": analytic,
        "surrogate": ml,
        "comparison": compare_effects(analytic, ml),
        "exposure": exposure,
    }
