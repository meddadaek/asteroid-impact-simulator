---
title: Orbital Sentinel
emoji: ☄️
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Near-Earth object impact prediction on a photoreal 3D globe
---

# Orbital Sentinel

An interactive near-Earth-object impact simulator. Enter an asteroid — either as
physical properties or as real Keplerian orbital elements — and it propagates the
orbit, decides whether Earth captures it, solves *where* on the rotating planet it
lands, and models what that does to the ground and the people on it.

**Source and full write-up:** https://github.com/meddadaek/asteroid-impact-simulator

## What it computes

Three layers, each checked against something real.

**Orbital mechanics.** Heliocentric Kepler propagation, solved by Newton–Raphson
from a Danby guess (residual `4e-16` at `e = 0.995`). Impact is decided by
gravitational focusing, `b_crit = R·√(1 + v_esc²/v_inf²)`, not geometric radius —
a slow body is captured from much further out than a fast one. The landing site
comes from solving the hyperbolic Earth encounter and rotating that point through
the obliquity and Greenwich sidereal time.

MOID — the closest the two orbit *ellipses* ever come — matches JPL's published
values to a median 0.000138 AU over 300 real objects.

**Impact physics.** Atmospheric entry is a numerical integration of the pancake
fragmentation model, then Collins–Melosh–Marcus scaling for crater, air blast,
thermal radiation, seismic magnitude and tsunami. Calibrated against real events
with no per-event tuning:

| Event | Model | Observed |
|---|---|---|
| Chelyabinsk 2013 energy | 0.52 Mt | ~0.5 Mt |
| Barringer Crater diameter | 1234 m | 1200 m |
| Chicxulub crater diameter | 164 km | ~180 km |

**Machine learning.** A gradient-boosted classifier predicts whether an orbit
strikes Earth from its six elements. Adding MOID as a feature moved ROC-AUC from
0.691 to 0.925 on identical data; at full size it reaches 0.944 and is well
calibrated — a predicted 37% really does strike 36% of the time. A second family
of models reproduces the damage physics, and the interface shows those predictions
**next to the analytic solution with the error percentage**, so the model's
accuracy stays visible rather than asserted.

## Honest limitations

Two-body propagation only — no planetary perturbations, no Yarkovsky. Real impact
monitoring uses full n-body integration, so predicted encounter distances drift
over decades. MOID, being phase-independent, stays accurate. Population figures
count cities over 15,000 people, so rural population is undercounted. Tsunami
modelling is order-of-magnitude only.

## Performance note

Astronomer mode runs a Monte Carlo over thousands of propagated clones. On the
free two-core tier that takes several seconds; lower the clone count if you want
it snappier.

## Data

JPL Small-Body Database · NASA CNEOS Sentry · GeoNames · NASA Visible Earth.
All free, no key, no account.

## Languages

English and Arabic, with full right-to-left layout.
