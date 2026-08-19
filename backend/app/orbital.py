"""Heliocentric Keplerian orbital mechanics and Earth-encounter geometry.

Everything works in the J2000 ecliptic frame, distances in AU, time in Julian
days, unless a function name says otherwise.

The pipeline this module implements:

    orbital elements  ->  heliocentric state vectors over time
                      ->  geocentric close approach (distance, v_inf)
                      ->  gravitational focusing test (impact / miss)
                      ->  hyperbolic encounter solution
                      ->  impact point on the rotating Earth (lat, lon)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from typing import Optional

import numpy as np

from constants import (
    AU, DAY, DEG, GM_SUN_AU, GM_EARTH, R_EARTH,
    OBLIQUITY, Z_ATMOSPHERE,
)

J2000 = 2451545.0

# Working-set target for the blocked propagation sweep, in (orbit x epoch)
# points. Tuned by measurement: far larger and the Kepler solve goes
# memory-bound, far smaller and interpreter overhead dominates again.
BLOCK_POINTS = 200_000


# ---------------------------------------------------------------------------
# Kepler equation solvers
# ---------------------------------------------------------------------------
def solve_kepler(M, e: float, tol: float = 1e-12, max_iter: int = 80):
    """Solve M = E - e*sin(E) for the eccentric anomaly E (elliptical, e<1).

    Newton-Raphson from a Danby-style starting guess, which converges in a
    handful of iterations even at e ~ 0.97 where the naive guess E0 = M stalls.
    """
    M = np.atleast_1d(np.asarray(M, dtype=float))
    M = np.mod(M + math.pi, 2 * math.pi) - math.pi          # wrap to [-pi, pi]
    E = M + 0.85 * e * np.sign(np.sin(M))                   # Danby guess
    for _ in range(max_iter):
        f = E - e * np.sin(E) - M
        fp = 1.0 - e * np.cos(E)
        dE = np.clip(-f / fp, -0.9, 0.9)   # damp early steps, near-parabolic
        E = E + dE
        if np.all(np.abs(dE) < tol):
            break
    return E


def solve_kepler_hyperbolic(M: float, e: float, tol: float = 1e-12,
                            max_iter: int = 200) -> float:
    """Solve M = e*sinh(H) - H for the hyperbolic anomaly H (e>1)."""
    H = math.asinh(M / e) if abs(M) > 6.0 else M / (e - 1.0)
    for _ in range(max_iter):
        f = e * math.sinh(H) - H - M
        fp = e * math.cosh(H) - 1.0
        dH = -f / fp
        H += dH
        if abs(dH) < tol:
            break
    return H


# ---------------------------------------------------------------------------
# Elements <-> state vectors
# ---------------------------------------------------------------------------
@dataclass
class Elements:
    """Classical heliocentric elements. Angles in degrees, a in AU, epoch in JD."""
    a: float            # semi-major axis, AU
    e: float            # eccentricity
    i: float            # inclination, deg
    om: float           # longitude of ascending node, deg
    w: float            # argument of perihelion, deg
    ma: float           # mean anomaly at epoch, deg
    epoch: float        # JD (TDB)

    def mean_motion(self) -> float:
        """Radians per day."""
        return math.sqrt(GM_SUN_AU / self.a ** 3)

    def period_days(self) -> float:
        return 2 * math.pi / self.mean_motion()

    def perihelion(self) -> float:
        return self.a * (1 - self.e)

    def aphelion(self) -> float:
        return self.a * (1 + self.e)

    def as_dict(self) -> dict:
        return asdict(self)


def _rotation_matrix(i: float, om: float, w: float) -> np.ndarray:
    """Perifocal -> ecliptic rotation, angles in radians (3-1-3 Euler)."""
    co, so = math.cos(om), math.sin(om)
    ci, si = math.cos(i), math.sin(i)
    cw, sw = math.cos(w), math.sin(w)
    return np.array([
        [co * cw - so * sw * ci, -co * sw - so * cw * ci,  so * si],
        [so * cw + co * sw * ci, -so * sw + co * cw * ci, -co * si],
        [sw * si,                 cw * si,                 ci     ],
    ])


def elements_to_state(el: Elements, jd):
    """Propagate elements to heliocentric position/velocity at Julian date(s).

    Returns (r, v) with shape (N, 3): r in AU, v in AU/day.
    """
    jd = np.atleast_1d(np.asarray(jd, dtype=float))
    n = el.mean_motion()
    M = el.ma * DEG + n * (jd - el.epoch)
    E = solve_kepler(M, el.e)

    cosE, sinE = np.cos(E), np.sin(E)
    b = el.a * math.sqrt(max(1.0 - el.e ** 2, 1e-15))

    # perifocal frame
    x_pf = el.a * (cosE - el.e)
    y_pf = b * sinE
    Edot = n / (1.0 - el.e * cosE)
    vx_pf = -el.a * sinE * Edot
    vy_pf = b * cosE * Edot

    R = _rotation_matrix(el.i * DEG, el.om * DEG, el.w * DEG)
    pf_r = np.stack([x_pf, y_pf, np.zeros_like(x_pf)], axis=-1)
    pf_v = np.stack([vx_pf, vy_pf, np.zeros_like(vx_pf)], axis=-1)
    return pf_r @ R.T, pf_v @ R.T


def state_to_elements(r: np.ndarray, v: np.ndarray, jd: float) -> Elements:
    """Invert state vectors (AU, AU/day) back to classical elements."""
    mu = GM_SUN_AU
    rn = float(np.linalg.norm(r))
    vn = float(np.linalg.norm(v))
    h = np.cross(r, v)
    hn = float(np.linalg.norm(h))
    nvec = np.cross([0.0, 0.0, 1.0], h)
    nn = float(np.linalg.norm(nvec))

    evec = ((vn ** 2 - mu / rn) * r - np.dot(r, v) * v) / mu
    e = float(np.linalg.norm(evec))
    energy = vn ** 2 / 2 - mu / rn
    a = -mu / (2 * energy)

    i = math.acos(float(np.clip(h[2] / hn, -1, 1)))
    om = math.atan2(nvec[1], nvec[0]) if nn > 1e-12 else 0.0
    if nn > 1e-12 and e > 1e-12:
        w = math.acos(float(np.clip(np.dot(nvec, evec) / (nn * e), -1, 1)))
    else:
        w = 0.0
    if evec[2] < 0:
        w = 2 * math.pi - w
    if e > 1e-12:
        nu = math.acos(float(np.clip(np.dot(evec, r) / (e * rn), -1, 1)))
    else:
        nu = 0.0
    if np.dot(r, v) < 0:
        nu = 2 * math.pi - nu
    E = 2 * math.atan2(math.sqrt(max(1 - e, 1e-15)) * math.sin(nu / 2),
                       math.sqrt(max(1 + e, 1e-15)) * math.cos(nu / 2))
    M = E - e * math.sin(E)
    return Elements(a=a, e=e, i=math.degrees(i), om=math.degrees(om) % 360,
                    w=math.degrees(w) % 360, ma=math.degrees(M) % 360, epoch=jd)


# ---------------------------------------------------------------------------
# Earth ephemeris (Standish approximate elements, good to ~arcmin 1800-2050)
# ---------------------------------------------------------------------------
_EARTH_EL = {         # value,        rate per Julian century
    "a":  (1.00000261,  0.00000562),
    "e":  (0.01671123, -0.00004392),
    "i":  (-0.00001531, -0.01294668),
    "L":  (100.46457166, 35999.37244981),
    "lp": (102.93768193, 0.32327364),     # longitude of perihelion
    "om": (0.0, 0.0),
}


def earth_elements(jd: float) -> Elements:
    T = (jd - J2000) / 36525.0
    val = {k: v0 + rate * T for k, (v0, rate) in _EARTH_EL.items()}
    return Elements(a=val["a"], e=val["e"], i=val["i"], om=val["om"],
                    w=(val["lp"] - val["om"]) % 360,
                    ma=(val["L"] - val["lp"]) % 360, epoch=jd)


def earth_state(jd):
    """Earth heliocentric state, AU and AU/day.

    Elements are re-evaluated at the midpoint of the requested span so the
    secular rates stay accurate across a long propagation window.
    """
    jd = np.atleast_1d(np.asarray(jd, dtype=float))
    el = earth_elements(float(np.mean(jd)))
    return elements_to_state(el, jd)


# ---------------------------------------------------------------------------
# Close approach search
# ---------------------------------------------------------------------------
@dataclass
class CloseApproach:
    jd: float
    distance_au: float
    distance_km: float
    v_inf_kms: float           # geocentric velocity far from Earth
    v_impact_kms: float        # after gravitational focusing, at atmosphere top
    b_crit_km: float           # capture radius including focusing
    impact: bool
    r_rel: tuple               # geocentric position at CA, AU (ecliptic)
    v_rel: tuple               # geocentric velocity at CA, AU/day (ecliptic)


def evaluate_encounter(el: Elements, jd: float) -> CloseApproach:
    """Full geometry of one close approach, including the focusing test."""
    r_a, v_a = elements_to_state(el, jd)
    r_e, v_e = earth_state(jd)
    r_rel = r_a[0] - r_e[0]                     # AU
    v_rel = v_a[0] - v_e[0]                     # AU/day

    dist_au = float(np.linalg.norm(r_rel))
    dist_km = dist_au * AU / 1000.0
    v_inf = float(np.linalg.norm(v_rel)) * AU / DAY      # m/s

    # Gravitational focusing: Earth capture cross-section radius
    #   b_crit = R * sqrt(1 + v_esc^2 / v_inf^2)
    r_capture = R_EARTH + Z_ATMOSPHERE
    v_esc_at = math.sqrt(2 * GM_EARTH / r_capture)
    b_crit = r_capture * math.sqrt(1.0 + (v_esc_at / max(v_inf, 1.0)) ** 2)
    v_impact = math.sqrt(v_inf ** 2 + v_esc_at ** 2)

    return CloseApproach(
        jd=jd,
        distance_au=dist_au,
        distance_km=dist_km,
        v_inf_kms=v_inf / 1000.0,
        v_impact_kms=v_impact / 1000.0,
        b_crit_km=b_crit / 1000.0,
        impact=(dist_km < b_crit / 1000.0),
        r_rel=tuple(float(x) for x in r_rel),
        v_rel=tuple(float(x) for x in v_rel),
    )


def _separation(el: Elements, jd: float) -> float:
    r_a, _ = elements_to_state(el, jd)
    r_e, _ = earth_state(jd)
    return float(np.linalg.norm(r_a[0] - r_e[0]))


def _golden_min(el: Elements, lo: float, hi: float, tol: float = 1e-6) -> float:
    """Golden-section search for the minimum-separation epoch."""
    invphi = (math.sqrt(5.0) - 1.0) / 2.0
    c = hi - invphi * (hi - lo)
    d = lo + invphi * (hi - lo)
    fc, fd = _separation(el, c), _separation(el, d)
    while abs(hi - lo) > tol:
        if fc < fd:
            hi, d, fd = d, c, fc
            c = hi - invphi * (hi - lo)
            fc = _separation(el, c)
        else:
            lo, c, fc = c, d, fd
            d = lo + invphi * (hi - lo)
            fd = _separation(el, d)
    return (lo + hi) / 2.0


def find_close_approaches(el: Elements, jd_start: float, years: float = 100.0,
                          coarse_step: float = 0.5,
                          max_results: int = 12) -> list:
    """Scan for local minima of the geocentric distance and refine each one.

    Coarse sampling at ``coarse_step`` days, then a golden-section refinement of
    every bracketed minimum. Relative motion during an encounter is at most
    ~0.03 AU/day, so a half-day grid brackets every minimum we care about.
    """
    jd_end = jd_start + years * 365.25
    grid = np.arange(jd_start, jd_end, coarse_step)
    r_a, _ = elements_to_state(el, grid)
    r_e, _ = earth_state(grid)
    d = np.linalg.norm(r_a - r_e, axis=1)

    interior = np.where((d[1:-1] < d[:-2]) & (d[1:-1] < d[2:]))[0] + 1
    if interior.size == 0:
        return []
    order = interior[np.argsort(d[interior])][: max_results * 4]

    results = []
    for idx in order:
        jd_min = _golden_min(el, float(grid[idx - 1]), float(grid[idx + 1]))
        ca = evaluate_encounter(el, jd_min)
        if any(abs(ca.jd - r.jd) < 5.0 for r in results):
            continue                       # same encounter, already recorded
        results.append(ca)
        if len(results) >= max_results:
            break
    results.sort(key=lambda c: c.distance_au)
    return results


# ---------------------------------------------------------------------------
# Where on Earth does it land?
# ---------------------------------------------------------------------------
def gmst_rad(jd: float) -> float:
    """Greenwich mean sidereal time (IAU 1982), radians."""
    T = (jd - J2000) / 36525.0
    gmst_sec = (67310.54841
                + (876600.0 * 3600.0 + 8640184.812866) * T
                + 0.093104 * T ** 2
                - 6.2e-6 * T ** 3)
    return (gmst_sec % 86400.0) / 86400.0 * 2 * math.pi


def ecliptic_to_equatorial(v: np.ndarray) -> np.ndarray:
    c, s = math.cos(OBLIQUITY), math.sin(OBLIQUITY)
    return np.array([v[0], c * v[1] - s * v[2], s * v[1] + c * v[2]])


def eci_to_geodetic(v_eci: np.ndarray, jd: float):
    """Unit vector in ECI -> (lat, lon) degrees on the rotating Earth."""
    theta = gmst_rad(jd)
    c, s = math.cos(theta), math.sin(theta)
    x = c * v_eci[0] + s * v_eci[1]
    y = -s * v_eci[0] + c * v_eci[1]
    z = v_eci[2]
    n = math.sqrt(x * x + y * y + z * z)
    lat = math.degrees(math.asin(max(-1.0, min(1.0, z / n))))
    lon = math.degrees(math.atan2(y, x))
    lon = ((lon + 180.0) % 360.0) - 180.0
    return lat, lon


@dataclass
class ImpactGeometry:
    latitude: float
    longitude: float
    entry_angle_deg: float          # from the local horizontal
    azimuth_deg: float              # compass bearing of the incoming track
    v_impact_kms: float
    jd: float
    impact_parameter_km: float


def _rodrigues(v: np.ndarray, axis: np.ndarray, theta: float) -> np.ndarray:
    """Rotate vector v about a unit axis by theta (Rodrigues formula)."""
    c, s = math.cos(theta), math.sin(theta)
    return v * c + np.cross(axis, v) * s + axis * float(np.dot(axis, v)) * (1 - c)


def _azimuth(r_hat: np.ndarray, v_hat: np.ndarray) -> float:
    """Compass bearing (deg from north) of v_hat at the surface point r_hat."""
    up = r_hat / np.linalg.norm(r_hat)
    north = np.array([0.0, 0.0, 1.0]) - up * up[2]
    n = float(np.linalg.norm(north))
    if n < 1e-9:
        return 0.0
    north /= n
    east = np.cross(up, north)
    horiz = v_hat - up * float(np.dot(up, v_hat))
    if np.linalg.norm(horiz) < 1e-12:
        return 0.0
    az = math.degrees(math.atan2(float(np.dot(horiz, east)),
                                 float(np.dot(horiz, north))))
    return (az + 360.0) % 360.0


def solve_impact_point(ca: CloseApproach, b_offset_km: Optional[float] = None,
                       b_azimuth_rad: float = 0.0) -> Optional[ImpactGeometry]:
    """Solve the hyperbolic Earth encounter and locate the surface impact point.

    The incoming asymptote direction and the impact parameter ``b`` define a
    hyperbola about Earth. We find the true anomaly at which the radius equals
    the entry interface, rotate that point into the equatorial frame, then into
    the Earth-fixed frame using GMST.

    ``b_offset_km`` overrides the impact parameter (the Monte Carlo uses this to
    sample the b-plane); ``b_azimuth_rad`` rotates the b-vector about the
    velocity axis, which is what sweeps the impact point around the globe.
    """
    v_rel = np.array(ca.v_rel) * AU / DAY           # m/s
    v_inf = float(np.linalg.norm(v_rel))
    if v_inf < 1.0:
        return None
    u_hat = v_rel / v_inf                            # incoming direction

    b = (ca.distance_km if b_offset_km is None else b_offset_km) * 1000.0
    mu = GM_EARTH
    r_entry = R_EARTH + Z_ATMOSPHERE

    # hyperbolic elements of the encounter
    h = b * v_inf                                    # specific angular momentum
    p = h ** 2 / mu                                  # semi-latus rectum
    e_hyp = math.sqrt(1.0 + (b * v_inf ** 2 / mu) ** 2)
    if p / (1.0 + e_hyp) > r_entry:
        return None                                  # misses the atmosphere

    # true anomaly where r = r_entry, inbound branch -> negative
    nu = -math.acos(max(-1.0, min(1.0, (p / r_entry - 1.0) / e_hyp)))
    nu_inf = -math.acos(max(-1.0, min(1.0, -1.0 / e_hyp)))
    dnu = nu - nu_inf

    # encounter plane basis: velocity axis and the impact-parameter direction
    ref = np.array([0.0, 0.0, 1.0])
    if abs(float(np.dot(ref, u_hat))) > 0.98:
        ref = np.array([1.0, 0.0, 0.0])
    e1 = np.cross(u_hat, ref)
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(u_hat, e1)
    b_hat = math.cos(b_azimuth_rad) * e1 + math.sin(b_azimuth_rad) * e2

    n_hat = np.cross(b_hat, u_hat)                   # orbit normal
    n_hat /= np.linalg.norm(n_hat)

    # far-field position direction is -u_hat; rotate it to the entry point
    d_entry = _rodrigues(-u_hat, n_hat, dnu)
    r_hat = d_entry / np.linalg.norm(d_entry)

    # flight-path angle: tan(gamma) = e sin(nu) / (1 + e cos(nu))
    gamma = math.atan2(e_hyp * math.sin(nu), 1.0 + e_hyp * math.cos(nu))
    entry_angle = max(1.0, min(90.0, abs(math.degrees(gamma))))

    eq = ecliptic_to_equatorial(r_hat)
    lat, lon = eci_to_geodetic(eq, ca.jd)

    v_dir = _rodrigues(u_hat, n_hat, dnu)
    az = _azimuth(eq, ecliptic_to_equatorial(v_dir))

    v_imp = math.sqrt(v_inf ** 2 + 2 * mu / r_entry)
    return ImpactGeometry(latitude=lat, longitude=lon,
                          entry_angle_deg=entry_angle, azimuth_deg=az,
                          v_impact_kms=v_imp / 1000.0, jd=ca.jd,
                          impact_parameter_km=b / 1000.0)


# ---------------------------------------------------------------------------
# Batch propagation -- many orbits at once, for dataset generation
# ---------------------------------------------------------------------------
def batch_positions(a, e, i, om, w, ma, epoch, jd):
    """Heliocentric positions for N orbits at N epochs (or one shared epoch).

    All inputs are arrays of shape (N,); ``jd`` may be scalar or (N,).
    Returns (N, 3) in AU. This is the hot loop of the dataset generator, so it
    builds the perifocal basis vectors directly instead of assembling per-orbit
    rotation matrices.
    """
    n_mot = np.sqrt(GM_SUN_AU / a ** 3)
    M = ma * DEG + n_mot * (np.asarray(jd) - epoch)
    E = solve_kepler(M, e)

    cosE, sinE = np.cos(E), np.sin(E)
    b = a * np.sqrt(np.maximum(1.0 - e ** 2, 1e-15))
    x_pf = a * (cosE - e)
    y_pf = b * sinE

    ci, si = np.cos(i * DEG), np.sin(i * DEG)
    co, so = np.cos(om * DEG), np.sin(om * DEG)
    cw, sw = np.cos(w * DEG), np.sin(w * DEG)

    Px = cw * co - sw * so * ci
    Py = cw * so + sw * co * ci
    Pz = sw * si
    Qx = -sw * co - cw * so * ci
    Qy = -sw * so + cw * co * ci
    Qz = cw * si

    return np.stack([x_pf * Px + y_pf * Qx,
                     x_pf * Py + y_pf * Qy,
                     x_pf * Pz + y_pf * Qz], axis=-1)


def batch_velocities(a, e, i, om, w, ma, epoch, jd):
    """Companion to :func:`batch_positions`, returning (N, 3) in AU/day."""
    n_mot = np.sqrt(GM_SUN_AU / a ** 3)
    M = ma * DEG + n_mot * (np.asarray(jd) - epoch)
    E = solve_kepler(M, e)

    cosE, sinE = np.cos(E), np.sin(E)
    b = a * np.sqrt(np.maximum(1.0 - e ** 2, 1e-15))
    Edot = n_mot / (1.0 - e * cosE)
    vx_pf = -a * sinE * Edot
    vy_pf = b * cosE * Edot

    ci, si = np.cos(i * DEG), np.sin(i * DEG)
    co, so = np.cos(om * DEG), np.sin(om * DEG)
    cw, sw = np.cos(w * DEG), np.sin(w * DEG)

    Px = cw * co - sw * so * ci
    Py = cw * so + sw * co * ci
    Pz = sw * si
    Qx = -sw * co - cw * so * ci
    Qy = -sw * so + cw * co * ci
    Qz = cw * si

    return np.stack([vx_pf * Px + vy_pf * Qx,
                     vx_pf * Py + vy_pf * Qy,
                     vx_pf * Pz + vy_pf * Qz], axis=-1)


def batch_earth_positions(jd):
    """Earth heliocentric positions at (N,) epochs, AU."""
    jd = np.asarray(jd, dtype=float)
    T = (jd - J2000) / 36525.0
    a = _EARTH_EL["a"][0] + _EARTH_EL["a"][1] * T
    e = _EARTH_EL["e"][0] + _EARTH_EL["e"][1] * T
    i = _EARTH_EL["i"][0] + _EARTH_EL["i"][1] * T
    L = _EARTH_EL["L"][0] + _EARTH_EL["L"][1] * T
    lp = _EARTH_EL["lp"][0] + _EARTH_EL["lp"][1] * T
    om = np.zeros_like(np.atleast_1d(T))
    return batch_positions(a, e, i, om, (lp - om) % 360, (L - lp) % 360, jd, jd)


def batch_earth_velocities(jd):
    jd = np.asarray(jd, dtype=float)
    T = (jd - J2000) / 36525.0
    a = _EARTH_EL["a"][0] + _EARTH_EL["a"][1] * T
    e = _EARTH_EL["e"][0] + _EARTH_EL["e"][1] * T
    i = _EARTH_EL["i"][0] + _EARTH_EL["i"][1] * T
    L = _EARTH_EL["L"][0] + _EARTH_EL["L"][1] * T
    lp = _EARTH_EL["lp"][0] + _EARTH_EL["lp"][1] * T
    om = np.zeros_like(np.atleast_1d(T))
    return batch_velocities(a, e, i, om, (lp - om) % 360, (L - lp) % 360, jd, jd)


def batch_closest_approach(elements: dict, jd_start: float, years: float = 30.0,
                           step_days: float = 1.0, refine_iters: int = 40,
                           chunk: int = 200000):
    """Minimum geocentric distance for a whole population of orbits.

    ``elements`` is a dict of (N,) arrays with keys a, e, i, om, w, ma, epoch.

    A coarse sweep on a ``step_days`` grid finds the bracketing epoch of the
    deepest approach, then a vectorised golden-section refinement pins the true
    minimum. Returns (min_distance_au, jd_of_min, v_inf_ms).
    """
    a = np.asarray(elements["a"], dtype=float)
    e = np.asarray(elements["e"], dtype=float)
    inc = np.asarray(elements["i"], dtype=float)
    om = np.asarray(elements["om"], dtype=float)
    w = np.asarray(elements["w"], dtype=float)
    ma = np.asarray(elements["ma"], dtype=float)
    ep = np.asarray(elements["epoch"], dtype=float)
    n = a.size

    best_d = np.full(n, np.inf)
    best_jd = np.full(n, jd_start)

    grid = np.arange(jd_start, jd_start + years * 365.25, step_days)

    # Sweep time in blocks rather than one epoch at a time. Stepping day by day
    # means ~11k Python iterations over small arrays, where interpreter overhead
    # dwarfs the arithmetic. Blocking amortises that, but only up to a point:
    # the Kepler solve allocates several temporaries per Newton iteration, so an
    # over-large block turns the loop into a memory-bandwidth problem instead.
    # Keeping each intermediate a couple of hundred thousand elements leaves the
    # working set in cache, which measures far faster than either extreme.
    block = max(1, int(BLOCK_POINTS // max(n, 1)))
    a_c, e_c = a[:, None], e[:, None]
    i_c, om_c, w_c = inc[:, None], om[:, None], w[:, None]
    ma_c, ep_c = ma[:, None], ep[:, None]

    for s in range(0, grid.size, block):
        t = grid[s:s + block]                                   # (T,)
        r_a = batch_positions(a_c, e_c, i_c, om_c, w_c, ma_c, ep_c, t)
        r_e = batch_earth_positions(t)                          # (T, 3)
        d = np.linalg.norm(r_a - r_e[None, :, :], axis=-1)       # (N, T)
        k = np.argmin(d, axis=1)
        dm = d[np.arange(n), k]
        better = dm < best_d
        best_d = np.where(better, dm, best_d)
        best_jd = np.where(better, t[k], best_jd)

    # vectorised golden-section refinement inside the bracketing interval
    invphi = (math.sqrt(5.0) - 1.0) / 2.0
    lo = best_jd - step_days
    hi = best_jd + step_days

    def sep(t):
        r_a = batch_positions(a, e, inc, om, w, ma, ep, t)
        r_e = batch_earth_positions(t)
        return np.linalg.norm(r_a - r_e, axis=1)

    for _ in range(refine_iters):
        c = hi - invphi * (hi - lo)
        d_ = lo + invphi * (hi - lo)
        left = sep(c) < sep(d_)
        hi = np.where(left, d_, hi)
        lo = np.where(left, lo, c)

    jd_min = 0.5 * (lo + hi)
    d_min = sep(jd_min)

    v_a = batch_velocities(a, e, inc, om, w, ma, ep, jd_min)
    v_e = batch_earth_velocities(jd_min)
    v_inf = np.linalg.norm(v_a - v_e, axis=1) * AU / DAY      # m/s

    return d_min, jd_min, v_inf


def _orbit_points(a, e, i, om, w, E):
    """Points on an orbit at eccentric anomalies E, without reference to time.

    ``a, e, i, om, w`` are (N, 1); ``E`` is (N, M). Returns (N, M, 3) in AU.
    """
    b = a * np.sqrt(np.maximum(1.0 - e ** 2, 1e-15))
    x_pf = a * (np.cos(E) - e)
    y_pf = b * np.sin(E)

    ci, si = np.cos(i * DEG), np.sin(i * DEG)
    co, so = np.cos(om * DEG), np.sin(om * DEG)
    cw, sw = np.cos(w * DEG), np.sin(w * DEG)

    Px = cw * co - sw * so * ci
    Py = cw * so + sw * co * ci
    Pz = sw * si
    Qx = -sw * co - cw * so * ci
    Qy = -sw * so + cw * co * ci
    Qz = cw * si

    return np.stack([x_pf * Px + y_pf * Qx,
                     x_pf * Py + y_pf * Qy,
                     x_pf * Pz + y_pf * Qz], axis=-1)


def batch_moid(a, e, i, om, w, jd_ref: float = J2000,
               n_coarse: int = 120, n_refine: int = 8,
               chunk: int = 800):
    """Minimum Orbit Intersection Distance against Earth, in AU.

    The MOID is the closest the two orbital *ellipses* come to each other,
    ignoring where the bodies actually are along them. It is the hard geometric
    prerequisite for an impact: no encounter can ever be closer than the MOID,
    however the phasing works out.

    Computed by a coarse double sweep over both eccentric anomalies, followed by
    a shrinking-window local refinement. Eight refinement rounds shrink the
    search window by 4^8, taking the angular resolution well below the scale
    that matters here.
    """
    a = np.atleast_1d(np.asarray(a, dtype=float))
    e = np.atleast_1d(np.asarray(e, dtype=float))
    i = np.atleast_1d(np.asarray(i, dtype=float))
    om = np.atleast_1d(np.asarray(om, dtype=float))
    w = np.atleast_1d(np.asarray(w, dtype=float))
    n = a.size

    eel = earth_elements(jd_ref)
    ea = np.array([eel.a]); ee = np.array([eel.e]); ei = np.array([eel.i])
    eom = np.array([eel.om]); ew = np.array([eel.w])

    grid = np.linspace(0.0, 2 * math.pi, n_coarse, endpoint=False)
    earth_pts = _orbit_points(ea[:, None], ee[:, None], ei[:, None],
                              eom[:, None], ew[:, None],
                              grid[None, :])[0]           # (M, 3)

    best_u = np.zeros(n)
    best_v = np.zeros(n)
    best_d = np.full(n, np.inf)

    for s in range(0, n, chunk):
        sl = slice(s, min(s + chunk, n))
        pts = _orbit_points(a[sl, None], e[sl, None], i[sl, None],
                            om[sl, None], w[sl, None],
                            grid[None, :])                # (C, M, 3)
        d = np.linalg.norm(pts[:, :, None, :] - earth_pts[None, None, :, :],
                           axis=-1)                       # (C, M, M)
        flat = d.reshape(d.shape[0], -1)
        k = np.argmin(flat, axis=1)
        best_d[sl] = flat[np.arange(flat.shape[0]), k]
        best_u[sl] = grid[k // n_coarse]
        best_v[sl] = grid[k % n_coarse]

    # local refinement: 7x7 probes in a window that shrinks by 4x each round
    window = 2 * math.pi / n_coarse
    offsets = np.linspace(-1.0, 1.0, 7)
    for _ in range(n_refine):
        u = best_u[:, None] + offsets[None, :] * window       # (N, 7)
        v = best_v[:, None] + offsets[None, :] * window
        pu = _orbit_points(a[:, None], e[:, None], i[:, None],
                           om[:, None], w[:, None], u)        # (N, 7, 3)
        pv = _orbit_points(np.repeat(ea, n)[:, None], np.repeat(ee, n)[:, None],
                           np.repeat(ei, n)[:, None], np.repeat(eom, n)[:, None],
                           np.repeat(ew, n)[:, None], v)      # (N, 7, 3)
        d = np.linalg.norm(pu[:, :, None, :] - pv[:, None, :, :], axis=-1)
        flat = d.reshape(n, -1)
        k = np.argmin(flat, axis=1)
        best_d = flat[np.arange(n), k]
        best_u = u[np.arange(n), k // 7]
        best_v = v[np.arange(n), k % 7]
        window *= 0.25

    return best_d


def batch_closest_approach_windows(elements: dict, centres, half_width: float,
                                   step_days: float = 0.25,
                                   refine_iters: int = 40):
    """Closest approach for a clone cloud, searched only near known encounters.

    A Monte-Carlo cloud is built by perturbing one orbit very slightly, so every
    clone meets Earth at very nearly the same epochs as the nominal orbit does.
    Sweeping all 30 years for each clone re-discovers that fact ten thousand
    times over. Instead the nominal orbit's encounter epochs are passed in as
    ``centres`` and each clone is only evaluated within ``half_width`` days of
    one, which is far wider than the along-track drift the perturbations can
    produce.

    Returns the same triple as :func:`batch_closest_approach`.
    """
    a = np.asarray(elements["a"], dtype=float)
    e = np.asarray(elements["e"], dtype=float)
    inc = np.asarray(elements["i"], dtype=float)
    om = np.asarray(elements["om"], dtype=float)
    w = np.asarray(elements["w"], dtype=float)
    ma = np.asarray(elements["ma"], dtype=float)
    ep = np.asarray(elements["epoch"], dtype=float)
    n = a.size

    grid = np.unique(np.concatenate([
        np.arange(c - half_width, c + half_width + step_days, step_days)
        for c in centres
    ]))

    a_c, e_c = a[:, None], e[:, None]
    i_c, om_c, w_c = inc[:, None], om[:, None], w[:, None]
    ma_c, ep_c = ma[:, None], ep[:, None]

    best_d = np.full(n, np.inf)
    best_jd = np.full(n, float(centres[0]))

    block = max(1, int(BLOCK_POINTS // max(n, 1)))
    for s in range(0, grid.size, block):
        t = grid[s:s + block]
        r_a = batch_positions(a_c, e_c, i_c, om_c, w_c, ma_c, ep_c, t)
        r_e = batch_earth_positions(t)
        d = np.linalg.norm(r_a - r_e[None, :, :], axis=-1)
        k = np.argmin(d, axis=1)
        dm = d[np.arange(n), k]
        better = dm < best_d
        best_d = np.where(better, dm, best_d)
        best_jd = np.where(better, t[k], best_jd)

    def sep(t):
        r_a = batch_positions(a, e, inc, om, w, ma, ep, t)
        r_e = batch_earth_positions(t)
        return np.linalg.norm(r_a - r_e, axis=1)

    invphi = (math.sqrt(5.0) - 1.0) / 2.0
    lo = best_jd - step_days
    hi = best_jd + step_days
    for _ in range(refine_iters):
        c = hi - invphi * (hi - lo)
        d_ = lo + invphi * (hi - lo)
        left = sep(c) < sep(d_)
        hi = np.where(left, d_, hi)
        lo = np.where(left, lo, c)

    jd_min = 0.5 * (lo + hi)
    d_min = sep(jd_min)
    v_a = batch_velocities(a, e, inc, om, w, ma, ep, jd_min)
    v_e = batch_earth_velocities(jd_min)
    v_inf = np.linalg.norm(v_a - v_e, axis=1) * AU / DAY
    return d_min, jd_min, v_inf


def capture_radius(v_inf_ms):
    """Earth gravitational capture radius (m) for a given v_inf (m/s)."""
    r_capture = R_EARTH + Z_ATMOSPHERE
    v_esc_at = math.sqrt(2 * GM_EARTH / r_capture)
    return r_capture * np.sqrt(1.0 + (v_esc_at / np.maximum(v_inf_ms, 1.0)) ** 2)


def sample_orbit_path(el: Elements, jd0: float, n: int = 512) -> list:
    """One full revolution of the orbit as a polyline, for the 3D scene."""
    period = el.period_days()
    jd = np.linspace(jd0, jd0 + period, n)
    r, _ = elements_to_state(el, jd)
    return [[float(p[0]), float(p[1]), float(p[2])] for p in r]
