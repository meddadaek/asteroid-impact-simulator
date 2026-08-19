"""Physical and astronomical constants (SI unless noted).

References
----------
Collins, G.S., Melosh, H.J., Marcus, R.A. (2005) "Earth Impact Effects Program:
    A Web-based computer program for calculating the regional environmental
    consequences of a meteoroid impact on Earth." Meteoritics & Planetary
    Science 40, 817-840.
Standish, E.M. (1992) "Keplerian Elements for Approximate Positions of the
    Major Planets." JPL Solar System Dynamics.
"""
import math

# --- Fundamental -------------------------------------------------------------
G = 6.67430e-11                  # gravitational constant, m^3 kg^-1 s^-2
AU = 1.495978707e11              # astronomical unit, m
DAY = 86400.0                    # s
YEAR = 365.25 * DAY              # Julian year, s
DEG = math.pi / 180.0

# --- Sun ---------------------------------------------------------------------
GM_SUN = 1.32712440018e20        # m^3 s^-2
# Gauss gravitational constant form: GM in AU^3 / day^2
GM_SUN_AU = GM_SUN * DAY**2 / AU**3

# --- Earth -------------------------------------------------------------------
M_EARTH = 5.97219e24             # kg
GM_EARTH = 3.986004418e14        # m^3 s^-2
R_EARTH = 6371000.0              # volumetric mean radius, m
R_EARTH_EQ = 6378137.0           # equatorial radius, m
V_ESCAPE = math.sqrt(2.0 * GM_EARTH / R_EARTH)     # 11.18 km/s
G_SURFACE = 9.81                 # m s^-2
OBLIQUITY = 23.43928 * DEG       # mean obliquity of the ecliptic at J2000
EARTH_ROT_RATE = 7.292115e-5     # rad/s (sidereal)
Z_ATMOSPHERE = 100000.0          # Karman line, m -- entry interface

# --- Atmosphere (exponential model used by Collins et al. 2005) --------------
RHO_AIR_0 = 1.225                # sea-level density, kg m^-3
SCALE_HEIGHT = 8000.0            # m
C_DRAG = 2.0                     # drag coefficient for a blunt body
FP_PANCAKE = 7.0                 # pancake dispersion factor at airburst

# --- Targets -----------------------------------------------------------------
RHO_TARGET_ROCK = 2750.0         # crystalline rock, kg m^-3
RHO_TARGET_SED = 2500.0          # sedimentary rock
RHO_WATER = 1000.0
MEAN_OCEAN_DEPTH = 3700.0        # global mean ocean depth, m
D_SIMPLE_COMPLEX = 3200.0        # simple->complex crater transition on Earth, m

# --- Impactor material presets ----------------------------------------------
IMPACTOR_TYPES = {
    "comet":       {"density": 500.0,  "label": "Porous comet nucleus"},
    "carbonaceous": {"density": 1500.0, "label": "Carbonaceous (C-type)"},
    "stony":       {"density": 3000.0, "label": "Stony (S-type)"},
    "stony_iron":  {"density": 5000.0, "label": "Stony-iron"},
    "iron":        {"density": 7800.0, "label": "Iron (M-type)"},
}

# --- Energy ------------------------------------------------------------------
J_PER_MEGATON = 4.184e15
J_PER_KILOTON = 4.184e12

# --- Reference events for calibration ---------------------------------------
# (used by tests/calibration to confirm the model reproduces reality)
REFERENCE_EVENTS = {
    "chelyabinsk_2013": {"diameter": 19.0, "density": 3300.0, "velocity": 19160.0,
                         "angle": 18.0, "observed_energy_mt": 0.5,
                         "observed_burst_km": 29.7},
    "tunguska_1908":    {"diameter": 60.0, "density": 2000.0, "velocity": 20000.0,
                         "angle": 45.0, "observed_energy_mt": 15.0,
                         "observed_burst_km": 8.0},
    "barringer_crater": {"diameter": 50.0, "density": 7800.0, "velocity": 12800.0,
                         "angle": 45.0, "observed_crater_m": 1200.0},
    "chicxulub_kpg":    {"diameter": 14000.0, "density": 2600.0, "velocity": 20000.0,
                         "angle": 60.0, "observed_crater_m": 180000.0},
}
