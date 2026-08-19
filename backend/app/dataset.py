"""Training-set generation.

Two independent datasets, both labelled by the physics modules:

``orbit``
    Features are the six Keplerian elements of a near-Earth object. The label is
    whether that orbit actually strikes Earth inside the horizon, determined by
    propagating it and testing the closest approach against Earth's
    gravitational capture radius.

    The interesting property of this task is that the impact/no-impact boundary
    in element space is extremely thin and convoluted -- a metre-per-second
    change in velocity moves the encounter by thousands of kilometres. A
    classifier cannot memorise that boundary, so its predicted probability
    converges on the fraction of orbits *in the neighbourhood* that strike,
    which is exactly the Monte-Carlo impact probability under observational
    uncertainty. That is what makes the surrogate useful rather than redundant.

``effects``
    Features are the impactor's physical properties, labels are the full entry +
    damage solution. Here the surrogate buys latency: the ODE integration is
    milliseconds, the tree ensemble is microseconds.

Positive examples are far too rare under naive sampling (roughly one in ten
million), so orbits are drawn from a mixture: two thirds bootstrapped from the
real JPL catalogue with noise, one third constructed backwards from a chosen
encounter geometry so that a near-miss is guaranteed.
"""
from __future__ import annotations

import json
import math
import os
import time

import numpy as np

from constants import AU, DAY, IMPACTOR_TYPES, J_PER_MEGATON
import orbital
from orbital import (Elements, batch_closest_approach, capture_radius,
                     state_to_elements, earth_state)
import impact as impact_mod

_HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(_HERE, "..", "data")
NEO_INDEX = os.path.join(DATA_DIR, "neo_index.json")

JD_BASE = 2461000.5          # 2025-12-27, the epoch the simulator runs from
HORIZON_YEARS = 30.0

ORBIT_FEATURES = [
    "a", "e", "i", "sin_om", "cos_om", "sin_w", "cos_w", "sin_ma", "cos_ma",
    "q", "Q", "period_yr", "tisserand", "dist_q_earth", "dist_Q_earth",
    "sin_i", "crosses_earth", "n_rev_per_earth_yr",
    "moid_au", "log_moid", "moid_vs_capture",
]


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------
def orbit_features(a, e, i, om, w, ma) -> np.ndarray:
    """Build the model's feature matrix from raw elements (all arrays)."""
    a = np.asarray(a, dtype=float)
    e = np.asarray(e, dtype=float)
    i = np.asarray(i, dtype=float)
    om = np.radians(np.asarray(om, dtype=float))
    w = np.radians(np.asarray(w, dtype=float))
    ma = np.radians(np.asarray(ma, dtype=float))

    q = a * (1 - e)
    Q = a * (1 + e)
    period_yr = a ** 1.5
    i_rad = np.radians(i)
    # Tisserand parameter with respect to Earth (a_E = 1 AU)
    tisserand = 1.0 / a + 2.0 * np.sqrt(a * (1 - e ** 2)) * np.cos(i_rad)
    crosses = ((q <= 1.0) & (Q >= 1.0)).astype(float)

    # The MOID is the closest the two orbit ellipses ever come, independent of
    # where the bodies sit along them. No encounter can beat it, so it is the
    # single strongest predictor available and worth its cost to compute.
    moid = orbital.batch_moid(a, e, i, np.degrees(om), np.degrees(w))
    # Earth's capture cross-section is ~1e-4 AU across; express the MOID in
    # those units so the model sees "how many Earth-capture-radii away is the
    # closest the orbits can ever get".
    moid_vs_capture = moid / 1.0e-4

    return np.column_stack([
        a, e, i,
        np.sin(om), np.cos(om), np.sin(w), np.cos(w), np.sin(ma), np.cos(ma),
        q, Q, period_yr, tisserand,
        np.abs(q - 1.0), np.abs(Q - 1.0),
        np.sin(i_rad), crosses, 1.0 / period_yr,
        moid, np.log10(np.maximum(moid, 1e-8)), moid_vs_capture,
    ])


# ---------------------------------------------------------------------------
# Orbit sampling
# ---------------------------------------------------------------------------
def _load_catalog() -> dict:
    with open(NEO_INDEX, "r", encoding="utf-8") as fh:
        idx = json.load(fh)
    rows = idx["featured"]
    return {k: np.array([r[k] for r in rows], dtype=float)
            for k in ("a", "e", "i", "om", "w", "ma", "epoch")}


def sample_catalog_orbits(n: int, rng: np.random.Generator) -> dict:
    """Bootstrap real NEO orbits and jitter them.

    The jitter is deliberately much larger than real observational uncertainty:
    it is there to fill element space around the observed population, not to
    represent any particular object's error bars.
    """
    cat = _load_catalog()
    m = cat["a"].size
    pick = rng.integers(0, m, size=n)
    a = cat["a"][pick] * np.exp(rng.normal(0, 0.10, n))
    e = np.clip(cat["e"][pick] + rng.normal(0, 0.05, n), 0.0, 0.95)
    i = np.abs(cat["i"][pick] + rng.normal(0, 4.0, n))
    om = rng.uniform(0, 360, n)
    w = rng.uniform(0, 360, n)
    ma = rng.uniform(0, 360, n)
    return {"a": a, "e": e, "i": np.minimum(i, 170.0), "om": om, "w": w,
            "ma": ma, "epoch": np.full(n, JD_BASE)}


def sample_encounter_orbits(n: int, rng: np.random.Generator) -> dict:
    """Construct orbits backwards from a chosen Earth encounter.

    Pick an encounter epoch, put the body at a small offset from Earth with a
    plausible relative velocity, then invert the state vector to elements. Every
    orbit produced this way passes close to Earth at least once, which is what
    makes the positive class reachable at all.
    """
    jd_enc = JD_BASE + rng.uniform(0.0, HORIZON_YEARS * 365.25, n)
    r_e = orbital.batch_earth_positions(jd_enc)
    v_e = orbital.batch_earth_velocities(jd_enc)

    # offset: log-uniform from 3000 km out to 3 million km
    offset_km = 10.0 ** rng.uniform(math.log10(3e3), math.log10(3e6), n)
    off_dir = rng.normal(size=(n, 3))
    off_dir /= np.linalg.norm(off_dir, axis=1, keepdims=True)
    r_ast = r_e + off_dir * (offset_km * 1000.0 / AU)[:, None]

    # relative velocity: 3-35 km/s, isotropic
    v_inf = rng.uniform(3e3, 35e3, n)
    v_dir = rng.normal(size=(n, 3))
    v_dir /= np.linalg.norm(v_dir, axis=1, keepdims=True)
    v_ast = v_e + v_dir * (v_inf * DAY / AU)[:, None]

    out = {k: np.zeros(n) for k in ("a", "e", "i", "om", "w", "ma", "epoch")}
    keep = np.zeros(n, dtype=bool)
    for k in range(n):
        el = state_to_elements(r_ast[k], v_ast[k], float(jd_enc[k]))
        if not (0.1 < el.a < 40.0) or not (0.0 <= el.e < 0.95):
            continue
        out["a"][k] = el.a; out["e"][k] = el.e; out["i"][k] = el.i
        out["om"][k] = el.om; out["w"][k] = el.w
        # re-reference the mean anomaly to the common base epoch
        n_mot = math.sqrt(orbital.GM_SUN_AU / el.a ** 3)
        out["ma"][k] = math.degrees(
            math.radians(el.ma) + n_mot * (JD_BASE - jd_enc[k])) % 360.0
        out["epoch"][k] = JD_BASE
        keep[k] = True

    return {k: v[keep] for k, v in out.items()}


def build_orbit_dataset(n_total: int = 60000, encounter_fraction: float = 0.45,
                        seed: int = 7, verbose: bool = True):
    """Generate features and impact labels for ``n_total`` orbits."""
    rng = np.random.default_rng(seed)
    n_enc = int(n_total * encounter_fraction)
    n_cat = n_total - n_enc

    if verbose:
        print(f"  sampling {n_cat} catalogue orbits and {n_enc} constructed encounters")
    cat = sample_catalog_orbits(n_cat, rng)
    enc = sample_encounter_orbits(int(n_enc * 1.15), rng)
    enc = {k: v[:n_enc] for k, v in enc.items()}

    el = {k: np.concatenate([cat[k], enc[k]]) for k in cat}
    n = el["a"].size

    t0 = time.time()
    if verbose:
        print(f"  propagating {n} orbits over {HORIZON_YEARS:.0f} years...")
    d_min, jd_min, v_inf = batch_closest_approach(
        el, JD_BASE, years=HORIZON_YEARS, step_days=1.0)
    if verbose:
        print(f"  propagation took {time.time()-t0:.1f}s")

    b_crit_au = capture_radius(v_inf) / AU
    hit = (d_min < b_crit_au).astype(np.int8)

    X = orbit_features(el["a"], el["e"], el["i"], el["om"], el["w"], el["ma"])
    meta = {
        "min_distance_au": d_min,
        "jd_min": jd_min,
        "v_inf_ms": v_inf,
        "capture_radius_au": b_crit_au,
    }
    if verbose:
        print(f"  {int(hit.sum())} impacts out of {n} "
              f"({100*hit.mean():.2f}% positive)")
    return X, hit, meta, el


# ---------------------------------------------------------------------------
# Impact-effects dataset
# ---------------------------------------------------------------------------
EFFECT_FEATURES = ["log_diameter", "density", "velocity_kms", "angle_deg",
                   "log_mass", "log_energy_mt", "target_density"]

EFFECT_TARGETS = [
    "log_energy_deposited_mt",
    "burst_altitude_km",
    "log_crater_diameter_m",
    "log_blast_20kpa_km",
    "log_blast_4kpa_km",
    "log_blast_1kpa_km",
    "log_thermal_3rd_km",
    "seismic_magnitude",
]

# Two targets do not exist for every impactor: a body that bursts in the air
# leaves no crater, and one that reaches the ground has no burst altitude.
# Fitting those on the full sample forces the regressor to straddle a cliff
# between real values and a sentinel, which wrecks its accuracy on both sides.
# Instead each is fitted only where it is defined, and gated at inference by the
# airburst classifier.
CONDITIONAL_TARGETS = {
    "burst_altitude_km": "airburst",
    "log_crater_diameter_m": "ground",
}


def build_effects_dataset(n: int = 200000, seed: int = 11, verbose: bool = True):
    """Sample impactors and label them with the full physics solution."""
    rng = np.random.default_rng(seed)

    # diameter: log-uniform from 1 m to 20 km
    diameter = 10.0 ** rng.uniform(0.0, np.log10(20000.0), n)
    # density: pick a material class, then jitter within it
    densities = np.array([v["density"] for v in IMPACTOR_TYPES.values()])
    density = densities[rng.integers(0, densities.size, n)]
    density = np.clip(density * np.exp(rng.normal(0, 0.15, n)), 300.0, 9000.0)
    # velocity: 11.2 km/s (escape) to 72 km/s (head-on retrograde limit)
    velocity = rng.uniform(11200.0, 72000.0, n)
    # entry angle: the isotropic-flux distribution peaks at 45 degrees
    angle = np.degrees(np.arcsin(np.sqrt(rng.uniform(0, 1, n))))
    angle = np.clip(angle, 2.0, 90.0)
    # target
    target_choices = np.array([2500.0, 2750.0, 1000.0])
    target_density = target_choices[rng.integers(0, 3, n)]

    if verbose:
        print(f"  integrating atmospheric entry for {n} impactors...")
    t0 = time.time()
    entry = impact_mod.atmospheric_entry(diameter, density, velocity, angle)
    if verbose:
        print(f"  entry integration took {time.time()-t0:.1f}s")

    e_dep = entry["energy_deposited_j"]
    e_mt = e_dep / J_PER_MEGATON
    zb = entry["burst_altitude_m"] / 1000.0
    airburst = entry["airburst"]
    v_ground = entry["velocity_ground"]

    cr = impact_mod.crater(diameter, density, np.maximum(v_ground, 1.0),
                           angle, target_density)
    crater_d = np.where(airburst | (v_ground < 100.0), 0.0,
                        cr["final_diameter_m"])

    zb_m = entry["burst_altitude_m"]
    r20 = impact_mod.blast_radius(e_dep, 20000.0, zb_m) / 1000.0
    r4 = impact_mod.blast_radius(e_dep, 4000.0, zb_m) / 1000.0
    r1 = impact_mod.blast_radius(e_dep, 1000.0, zb_m) / 1000.0
    th3 = impact_mod.thermal_radius(
        e_dep, impact_mod.THERMAL_THRESHOLDS["burns_3rd_degree"], zb_m) / 1000.0
    mag = impact_mod.seismic_magnitude(e_dep)

    mass = entry["mass_kg"]
    e_init_mt = entry["energy_initial_j"] / J_PER_MEGATON

    X = np.column_stack([
        np.log10(diameter), density, velocity / 1000.0, angle,
        np.log10(mass), np.log10(e_init_mt), target_density,
    ])

    def lg(v):
        return np.log10(np.maximum(np.asarray(v, dtype=float), 1e-6))

    Y = np.column_stack([
        lg(e_mt), zb, lg(crater_d), lg(r20), lg(r4), lg(r1), lg(th3), mag,
    ])
    return X, Y, airburst.astype(np.int8)
