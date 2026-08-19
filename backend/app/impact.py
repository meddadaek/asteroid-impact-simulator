"""Atmospheric entry and impact-effect physics.

Two stages:

1. **Entry.** A vectorised numerical integration of the pancake (Hills & Goda
   1993; Chyba et al. 1993) fragmentation model down an exponential atmosphere.
   This replaces the closed-form approximations of Collins et al. (2005) with a
   direct ODE solve, which is both more accurate and easier to justify. It runs
   on whole batches at once so the training-set generator can push 200k entries
   through it in seconds.

2. **Effects.** Crater, seismic, thermal, air-blast, ejecta and tsunami scaling
   from Collins, Melosh & Marcus (2005), Meteoritics & Planetary Science 40,
   817-840, which is the peer-reviewed basis of the NASA/Imperial "Earth Impact
   Effects Program".

Every public function accepts scalars or numpy arrays and returns arrays.
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np

from constants import (
    RHO_AIR_0, SCALE_HEIGHT, C_DRAG, FP_PANCAKE, G_SURFACE,
    RHO_TARGET_ROCK, RHO_TARGET_SED, RHO_WATER, D_SIMPLE_COMPLEX,
    MEAN_OCEAN_DEPTH,
    J_PER_MEGATON, J_PER_KILOTON, Z_ATMOSPHERE, R_EARTH,
)

TARGETS = {
    "sedimentary": RHO_TARGET_SED,
    "crystalline": RHO_TARGET_ROCK,
    "water":       RHO_WATER,
}


def air_density(z):
    """Exponential atmosphere, kg/m^3. z in metres above sea level."""
    return RHO_AIR_0 * np.exp(-np.maximum(z, 0.0) / SCALE_HEIGHT)


def yield_strength(rho_i):
    """Aerodynamic yield strength of the body, Pa (Collins et al. 2005 eq. 10)."""
    return 10.0 ** (2.107 + 0.0624 * np.sqrt(rho_i))


# ---------------------------------------------------------------------------
# Stage 1 -- atmospheric entry
# ---------------------------------------------------------------------------
def atmospheric_entry(diameter, density, velocity, angle_deg,
                      n_steps: int = 900, z_top: float = Z_ATMOSPHERE):
    """Integrate entry from the top of the atmosphere to the ground.

    Parameters are broadcast against each other, so passing arrays of length N
    integrates N independent entries simultaneously.

    diameter : m, density : kg/m^3, velocity : m/s at the entry interface,
    angle_deg : degrees from the local horizontal.

    Returns a dict of arrays:
        energy_initial_j     kinetic energy entering the atmosphere
        energy_deposited_j   energy released as blast/thermal (the "yield")
        energy_ground_j      kinetic energy surviving to the surface
        velocity_ground      m/s at sea level (0 if fully ablated/burst)
        burst_altitude_m     altitude of peak energy deposition (0 = ground)
        airburst             bool, True when the body does not survive intact
        fragmented           bool, True when dynamic pressure exceeded strength
        pancake_ratio        final spread diameter / initial diameter
        peak_decel_g         peak deceleration in Earth gravities
    """
    L0 = np.atleast_1d(np.asarray(diameter, dtype=float))
    rho_i = np.atleast_1d(np.asarray(density, dtype=float))
    v0 = np.atleast_1d(np.asarray(velocity, dtype=float))
    theta = np.radians(np.atleast_1d(np.asarray(angle_deg, dtype=float)))
    L0, rho_i, v0, theta = np.broadcast_arrays(L0, rho_i, v0, theta)
    L0 = L0.astype(float).copy()
    rho_i = rho_i.astype(float).copy()
    v0 = v0.astype(float).copy()
    theta = np.clip(theta.astype(float).copy(), math.radians(0.5), math.pi / 2)

    n = L0.size
    sin_t = np.sin(theta)
    mass = rho_i * math.pi / 6.0 * L0 ** 3
    strength = yield_strength(rho_i)

    v = v0.copy()
    L = L0.copy()
    u = np.zeros(n)                           # transverse spreading rate, m/s
    fragmented = np.zeros(n, dtype=bool)
    landed = np.zeros(n, dtype=bool)          # reached the ground still moving

    dz = z_top / n_steps
    z_grid = np.linspace(z_top, 0.0, n_steps + 1)

    e_prev = 0.5 * mass * v ** 2
    energy_initial = e_prev.copy()
    max_dedz = np.zeros(n)
    burst_alt = np.zeros(n)
    peak_decel = np.zeros(n)

    for k in range(n_steps):
        z = z_grid[k]
        rho_a = air_density(z)

        alive = ~landed
        if not np.any(alive):
            break

        area = math.pi / 4.0 * L ** 2
        # deceleration along the flight path, m/s^2
        decel = C_DRAG * rho_a * area * v ** 2 / (2.0 * mass)
        peak_decel = np.maximum(peak_decel, decel / G_SURFACE)

        # dv/dz = decel/(v sin t) - g/v  ; integrate downward (dz < 0)
        dvdz = decel / (v * sin_t) - G_SURFACE / np.maximum(v, 1.0)
        v_new = v - dvdz * dz
        v_new = np.maximum(v_new, 0.0)

        # fragmentation once ram pressure beats the material strength
        fragmented |= (rho_a * v ** 2 > strength)

        # Pancake spreading (Chyba et al. 1993): the fragment cloud is pushed
        # apart by the ram pressure gradient, so the transverse rate u
        # accelerates from rest rather than jumping to its terminal value:
        #     du/dt = Cd rho_a v^2 / (rho_i L),   dL/dt = u
        # Integrating downward in altitude (ds = -dz/sin t):
        du = C_DRAG * rho_a * v * dz / (rho_i * np.maximum(L, 1e-6) * sin_t)
        u_new = np.where(fragmented, u + du, u)
        L_new = np.where(fragmented, L + u_new * dz / (v * sin_t), L)
        # cap the spread at the catastrophic-disruption ratio
        L_new = np.minimum(L_new, FP_PANCAKE * L0)

        e_new = 0.5 * mass * v_new ** 2
        dedz = (e_prev - e_new) / dz            # J per metre of altitude
        better = alive & (dedz > max_dedz)
        max_dedz = np.where(better, dedz, max_dedz)
        burst_alt = np.where(better, z, burst_alt)

        stopped = alive & (v_new <= 1.0)
        landed |= stopped

        v = np.where(landed, v, v_new)
        L = np.where(landed, L, L_new)
        u = np.where(landed, u, u_new)
        e_prev = np.where(landed, e_prev, e_new)

    v_ground = np.where(landed, 0.0, v)
    energy_ground = 0.5 * mass * v_ground ** 2

    # A surface impact is one where the body still carries a meaningful share of
    # its energy to sea level. Otherwise the burst altitude is where the bulk of
    # the energy went into the air.
    surviving_fraction = energy_ground / np.maximum(energy_initial, 1e-30)
    is_airburst = (surviving_fraction < 0.10) | (burst_alt > 1000.0)
    is_airburst &= (v_ground < 0.999 * v0)
    # a body that never fragmented and arrives fast always craters
    is_airburst &= ~((~fragmented) & (surviving_fraction > 0.05))

    burst_altitude = np.where(is_airburst, burst_alt, 0.0)
    # yield available to blast/thermal
    energy_deposited = np.where(is_airburst,
                                energy_initial - energy_ground,
                                energy_ground)
    energy_deposited = np.maximum(energy_deposited, 1e-30)

    return {
        "energy_initial_j": energy_initial,
        "energy_deposited_j": energy_deposited,
        "energy_ground_j": energy_ground,
        "velocity_ground": v_ground,
        "burst_altitude_m": burst_altitude,
        "airburst": is_airburst,
        "fragmented": fragmented,
        "pancake_ratio": L / L0,
        "peak_decel_g": peak_decel,
        "mass_kg": mass,
    }


# ---------------------------------------------------------------------------
# Stage 2 -- crater
# ---------------------------------------------------------------------------
def crater(diameter, density, v_ground, angle_deg, rho_target=RHO_TARGET_SED):
    """Transient and final crater from pi-group scaling (Collins eq. 21-22).

    Dtc = 1.161 (rho_i/rho_t)^(1/3) L^0.78 v^0.44 g^-0.22 sin(theta)^(1/3)
    """
    L = np.asarray(diameter, dtype=float)
    rho_i = np.asarray(density, dtype=float)
    v = np.maximum(np.asarray(v_ground, dtype=float), 1.0)
    theta = np.radians(np.clip(np.asarray(angle_deg, dtype=float), 0.5, 90.0))

    d_tc = (1.161 * (rho_i / rho_target) ** (1.0 / 3.0)
            * L ** 0.78 * v ** 0.44 * G_SURFACE ** -0.22
            * np.sin(theta) ** (1.0 / 3.0))
    depth_tc = d_tc / (2.0 * math.sqrt(2.0))

    simple = 1.25 * d_tc
    complex_ = 1.17 * d_tc ** 1.13 / D_SIMPLE_COMPLEX ** 0.13
    d_final = np.where(simple < D_SIMPLE_COMPLEX, simple, complex_)

    # rim-to-floor depth: simple craters ~ D/5, complex craters flatten out
    depth_final = np.where(simple < D_SIMPLE_COMPLEX,
                           d_final / 5.0,
                           0.4 * d_final ** 0.3)
    return {
        "transient_diameter_m": d_tc,
        "transient_depth_m": depth_tc,
        "final_diameter_m": d_final,
        "final_depth_m": depth_final,
        "is_complex": simple >= D_SIMPLE_COMPLEX,
    }


def ejecta_thickness(d_tc, r):
    """Ejecta blanket thickness at range r (Collins eq. 65), metres."""
    d_tc = np.asarray(d_tc, dtype=float)
    r = np.maximum(np.asarray(r, dtype=float), 1.0)
    return d_tc ** 4 / (112.0 * r ** 3)


# ---------------------------------------------------------------------------
# Stage 2 -- seismic
# ---------------------------------------------------------------------------
def seismic_magnitude(energy_j):
    """Richter magnitude of the impact-induced quake (Collins eq. 32)."""
    e = np.maximum(np.asarray(energy_j, dtype=float), 1.0)
    return 0.67 * np.log10(e) - 5.87


def seismic_at_range(magnitude, r_km):
    """Effective magnitude felt at range r (Collins eq. 33)."""
    m = np.asarray(magnitude, dtype=float)
    r = np.maximum(np.asarray(r_km, dtype=float), 0.1)
    near = m - 0.0238 * r
    mid = m - 0.0048 * r - 1.1644
    far = m - 1.66 * np.log10(np.radians(r / 111.32)) - 6.399
    return np.where(r < 60.0, near, np.where(r < 700.0, mid, far))


# ---------------------------------------------------------------------------
# Stage 2 -- thermal radiation
# ---------------------------------------------------------------------------
THERMAL_ETA = 3.0e-3          # luminous efficiency (Collins et al. 2005)

# thermal exposure thresholds, J/m^2, scaled as E_Mt^(1/6) (Collins table 1)
THERMAL_THRESHOLDS = {
    "burns_1st_degree":   0.13e6,
    "burns_2nd_degree":   0.33e6,
    "burns_3rd_degree":   0.67e6,
    "grass_ignites":      0.38e6,
    "clothing_ignites":   1.00e6,
    "plywood_ignites":    0.67e6,
    "trees_ignite":       0.25e6,
}


def fireball_radius(energy_j):
    """Radius of the luminous fireball, metres (Collins eq. 37)."""
    e = np.maximum(np.asarray(energy_j, dtype=float), 1.0)
    return 0.002 * e ** (1.0 / 3.0)


def thermal_radius(energy_j, threshold_j_m2, burst_altitude=0.0):
    """Ground range at which the thermal exposure equals a threshold.

    Exposure  Phi = eta E / (2 pi R^2)  with R the slant range from the fireball.
    Returns 0 where the fireball never delivers that much energy, and clips at
    the horizon, beyond which the fireball is not in view.
    """
    e = np.maximum(np.asarray(energy_j, dtype=float), 1.0)
    e_mt = e / J_PER_MEGATON
    phi = np.asarray(threshold_j_m2, dtype=float) * e_mt ** (1.0 / 6.0)
    slant_sq = THERMAL_ETA * e / (2.0 * math.pi * np.maximum(phi, 1e-30))
    zb = np.asarray(burst_altitude, dtype=float)
    ground_sq = slant_sq - zb ** 2
    r = np.where(ground_sq > 0.0, np.sqrt(np.maximum(ground_sq, 0.0)), 0.0)

    # horizon limit: the fireball top must still be above the local horizon
    r_f = fireball_radius(e)
    h_eff = np.maximum(zb + r_f, 1.0)
    r_horizon = np.sqrt(2.0 * R_EARTH * h_eff)
    return np.minimum(r, r_horizon)


# ---------------------------------------------------------------------------
# Stage 2 -- air blast
# ---------------------------------------------------------------------------
# Damage thresholds in peak overpressure (Pa)
BLAST_THRESHOLDS = {
    "windows_shatter":        1000.0,
    "trees_blown_down":       4000.0,
    "homes_collapse":        20000.0,
    "concrete_buildings":    70000.0,
    "total_destruction":    200000.0,
}


def overpressure(r, energy_j, burst_altitude=0.0):
    """Peak overpressure (Pa) at ground range r from the impact point.

    Collins et al. (2005) eq. 54 for a surface burst:

        p(R) = p_x r_x / (4R) * (1 + 3 (r_x/R)^1.3),
        r_x  = 290 m * E_kt^(1/3),  p_x = 75 kPa

    For an airburst the same relation is evaluated at the slant range from the
    burst point. That correctly removes the singularity over ground zero and
    tends to the surface-burst result far away. It does under-predict the
    mid-field Mach-stem enhancement by up to a factor ~2, which is the standard
    trade for not carrying full height-of-burst tables.
    """
    r = np.asarray(r, dtype=float)
    e_kt = np.maximum(np.asarray(energy_j, dtype=float) / J_PER_KILOTON, 1e-12)
    zb = np.asarray(burst_altitude, dtype=float)

    R = np.sqrt(r ** 2 + zb ** 2)
    R = np.maximum(R, 1.0)
    r_x = 290.0 * e_kt ** (1.0 / 3.0)
    p_x = 75000.0
    return p_x * r_x / (4.0 * R) * (1.0 + 3.0 * (r_x / R) ** 1.3)


def blast_radius(energy_j, pressure_pa, burst_altitude=0.0):
    """Invert the overpressure relation for the ground range at a given p.

    Bisection on log-range: the relation is monotonic in R, so 60 halvings pin
    the radius to well under a metre over the whole 1 m - 20000 km bracket.
    """
    e = np.atleast_1d(np.asarray(energy_j, dtype=float))
    p = np.atleast_1d(np.asarray(pressure_pa, dtype=float))
    zb = np.atleast_1d(np.asarray(burst_altitude, dtype=float))
    e, p, zb = np.broadcast_arrays(e, p, zb)

    lo = np.full(e.shape, 0.0)
    hi = np.full(e.shape, 2.0e7)          # 20 000 km, half Earth circumference
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        too_strong = overpressure(mid, e, zb) > p
        lo = np.where(too_strong, mid, lo)
        hi = np.where(too_strong, hi, mid)
    r = 0.5 * (lo + hi)
    # if even ground zero never reaches the threshold, there is no such radius
    return np.where(overpressure(np.zeros_like(r), e, zb) < p, 0.0, r)


def wind_speed(pressure_pa):
    """Peak wind velocity behind the shock, m/s (Collins eq. 57)."""
    p = np.asarray(pressure_pa, dtype=float)
    p0 = 101325.0
    return (5.0 * p / (7.0 * p0)) / np.sqrt(1.0 + 6.0 * p / (7.0 * p0)) * 340.3


# ---------------------------------------------------------------------------
# Stage 2 -- tsunami (ocean impacts)
# ---------------------------------------------------------------------------
def tsunami(d_tc, water_depth=4000.0, ranges_km=None):
    """Deep-water wave amplitude vs range for an ocean impact.

    The rim wave starts at roughly 0.07 of the transient crater diameter at the
    crater rim and decays as 1/r as it spreads radially. Shoaling at a coastline
    typically amplifies the deep-water amplitude by a factor of a few; a factor
    of 3 is applied for the reported run-up. Order-of-magnitude only.
    """
    d_tc = float(np.asarray(d_tc).ravel()[0])
    if ranges_km is None:
        ranges_km = [100, 300, 1000, 3000]
    r_rim = max(d_tc / 2.0, 1.0)
    a_rim = 0.07 * min(d_tc, water_depth * 4.0)
    out = []
    for rk in ranges_km:
        r = max(rk * 1000.0, r_rim)
        amp = a_rim * r_rim / r
        out.append({"range_km": rk,
                    "deep_water_amplitude_m": round(float(amp), 2),
                    "estimated_runup_m": round(float(amp * 3.0), 2)})
    return out


# ---------------------------------------------------------------------------
# Full effect assembly
# ---------------------------------------------------------------------------
def impact_effects(diameter, density, velocity, angle_deg,
                   target: str = "sedimentary") -> dict:
    """End-to-end: entry integration plus every downstream effect.

    Scalar in, scalar out. This is the analytic ground truth that the ML
    surrogate is trained against.
    """
    # A crater is excavated from the seafloor, not from the water column, so
    # ocean impacts are scaled against rock. The water still matters twice: the
    # impactor has to punch through it before it can touch the bottom, and it is
    # what carries the tsunami away.
    rho_t = RHO_TARGET_SED if target == "water" else TARGETS.get(target,
                                                                RHO_TARGET_SED)
    entry = atmospheric_entry(diameter, density, velocity, angle_deg)
    idx = 0

    def s(key):
        return float(np.asarray(entry[key]).ravel()[idx])

    airburst = bool(np.asarray(entry["airburst"]).ravel()[idx])
    e_dep = s("energy_deposited_j")
    e_init = s("energy_initial_j")
    v_ground = s("velocity_ground")
    zb = s("burst_altitude_m")

    result = {
        "airburst": airburst,
        "fragmented": bool(np.asarray(entry["fragmented"]).ravel()[idx]),
        "burst_altitude_km": zb / 1000.0,
        "energy_initial_mt": e_init / J_PER_MEGATON,
        "energy_deposited_mt": e_dep / J_PER_MEGATON,
        "velocity_ground_kms": v_ground / 1000.0,
        "peak_deceleration_g": s("peak_decel_g"),
        "mass_kg": s("mass_kg"),
        "pancake_ratio": s("pancake_ratio"),
    }

    # --- crater (only if something solid reaches the ground) ---
    if not airburst and v_ground > 100.0:
        cr = crater(diameter, density, v_ground, angle_deg, rho_t)
        depth = float(np.asarray(cr["transient_depth_m"]).ravel()[0])
        # In the open ocean, only an impactor big enough to excavate deeper than
        # the water column leaves a seafloor crater at all; anything smaller
        # spends itself making waves.
        if target == "water" and depth < MEAN_OCEAN_DEPTH:
            result["crater"] = None
            result["absorbed_by_ocean"] = True
            cr = None
    else:
        cr = None

    if cr is not None:
        result["crater"] = {
            "transient_diameter_m": float(np.asarray(cr["transient_diameter_m"]).ravel()[0]),
            "final_diameter_m": float(np.asarray(cr["final_diameter_m"]).ravel()[0]),
            "final_depth_m": float(np.asarray(cr["final_depth_m"]).ravel()[0]),
            "is_complex": bool(np.asarray(cr["is_complex"]).ravel()[0]),
        }
    else:
        result["crater"] = None

    # --- seismic ---
    mag = float(np.asarray(seismic_magnitude(e_dep)).ravel()[0])
    result["seismic"] = {
        "magnitude": mag,
        "felt_radius_km": float(np.asarray(
            _seismic_felt_radius(mag)).ravel()[0]),
    }

    # --- thermal ---
    thermal = {}
    for name, thresh in THERMAL_THRESHOLDS.items():
        thermal[name + "_km"] = float(
            np.asarray(thermal_radius(e_dep, thresh, zb)).ravel()[0]) / 1000.0
    thermal["fireball_radius_km"] = float(
        np.asarray(fireball_radius(e_dep)).ravel()[0]) / 1000.0
    result["thermal"] = thermal

    # --- blast ---
    blast = {}
    for name, p in BLAST_THRESHOLDS.items():
        blast[name + "_km"] = float(
            np.asarray(blast_radius(e_dep, p, zb)).ravel()[0]) / 1000.0
    result["blast"] = blast

    # --- tsunami ---
    # The wave is generated by the cavity punched in the *water*, which exists
    # whether or not the seafloor is ever touched, so it is scaled separately
    # against water density.
    if target == "water" and not airburst and v_ground > 100.0:
        water_cav = crater(diameter, density, v_ground, angle_deg, RHO_WATER)
        d_cav = float(np.asarray(water_cav["transient_diameter_m"]).ravel()[0])
        result["water_cavity_m"] = d_cav
        result["tsunami"] = tsunami(d_cav, MEAN_OCEAN_DEPTH)
    elif target == "water":
        result["tsunami"] = []
    else:
        result["tsunami"] = None

    # --- headline severity ---
    result["severity"] = classify_severity(result)
    return result


def _seismic_felt_radius(magnitude, felt_threshold: float = 4.0):
    """Range at which the effective magnitude drops to 'widely felt' (M4)."""
    m = np.atleast_1d(np.asarray(magnitude, dtype=float))
    lo = np.zeros_like(m)
    hi = np.full_like(m, 20000.0)
    for _ in range(50):
        mid = 0.5 * (lo + hi)
        strong = seismic_at_range(m, mid) > felt_threshold
        lo = np.where(strong, mid, lo)
        hi = np.where(strong, hi, mid)
    return 0.5 * (lo + hi)


SEVERITY_LEVELS = [
    (1e-3,  "negligible",   "Burns up high in the atmosphere. A bright fireball, nothing more."),
    (1.0,   "local",        "Airburst audible and visible for hundreds of kilometres. Broken windows."),
    (50.0,  "city",         "Destroys a metropolitan area. Comparable to the largest nuclear weapons."),
    (1e4,   "regional",     "Devastates a region the size of a small country."),
    (1e6,   "continental",  "Continental-scale destruction and multi-year climate disruption."),
    (1e9,   "global",       "Global catastrophe. Mass extinction territory."),
]


def classify_severity(result: dict) -> dict:
    e = result["energy_deposited_mt"]
    for threshold, key, description in SEVERITY_LEVELS:
        if e < threshold:
            return {"level": key, "description": description,
                    "energy_mt": e}
    return {"level": "extinction",
            "description": "Sterilising impact. Larger than anything in the geological record.",
            "energy_mt": e}
