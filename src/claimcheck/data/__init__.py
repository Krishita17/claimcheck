"""Synthetic data generation and the mock registry oracle fixtures."""

from .synth_org import (
    SyntheticName,
    SyntheticOrg,
    generate_org,
    CATEGORIES,
)

__all__ = [
    "SyntheticName",
    "SyntheticOrg",
    "generate_org",
    "CATEGORIES",
]
