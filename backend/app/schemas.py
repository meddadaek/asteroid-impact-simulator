"""Request and response models for the HTTP API."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Material = Literal["comet", "carbonaceous", "stony", "stony_iron", "iron"]
Uncertainty = Literal["precise", "good", "moderate", "poor"]


class ImpactorSpec(BaseModel):
    """Physical description of the incoming body."""
    diameter_m: float = Field(150.0, gt=0.1, le=100000.0)
    material: Material = "stony"
    density_kgm3: Optional[float] = Field(None, gt=100.0, le=12000.0)


class SimpleRequest(ImpactorSpec):
    """Simple mode: the user states the impact directly."""
    velocity_kms: float = Field(19.0, ge=11.2, le=72.0)
    angle_deg: float = Field(45.0, gt=0.0, le=90.0)
    latitude: float = Field(36.75, ge=-90.0, le=90.0)
    longitude: float = Field(3.06, ge=-180.0, le=180.0)
    azimuth_deg: float = Field(0.0, ge=0.0, lt=360.0)


class ElementsRequest(ImpactorSpec):
    """Astronomer mode: a real heliocentric orbit."""
    a: float = Field(1.2, gt=0.05, le=60.0, description="semi-major axis, AU")
    e: float = Field(0.35, ge=0.0, le=0.995, description="eccentricity")
    i: float = Field(5.0, ge=0.0, le=180.0, description="inclination, deg")
    om: float = Field(120.0, ge=0.0, lt=360.0, description="ascending node, deg")
    w: float = Field(60.0, ge=0.0, lt=360.0, description="arg. perihelion, deg")
    ma: float = Field(0.0, ge=0.0, lt=360.0, description="mean anomaly, deg")
    epoch: Optional[float] = Field(None, description="JD; defaults to the sim epoch")

    uncertainty: Uncertainty = "moderate"
    n_clones: int = Field(3000, ge=200, le=20000)
    horizon_years: float = Field(30.0, ge=1.0, le=100.0)
    force_impact: bool = Field(
        True, description="if it misses, show where it would have struck")


class EffectsRequest(ImpactorSpec):
    """Fast path for slider dragging: damage profile only, no orbit work."""
    velocity_kms: float = Field(19.0, ge=1.0, le=72.0)
    angle_deg: float = Field(45.0, gt=0.0, le=90.0)
    target: Literal["sedimentary", "crystalline", "water"] = "sedimentary"
    use_surrogate: bool = True
