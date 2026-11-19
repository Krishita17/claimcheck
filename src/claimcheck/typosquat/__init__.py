"""Typosquat-adjacency detection (a related attack to dependency confusion)."""

from .adjacency import (
    TyposquatDetector,
    generate_candidates,
    edit_distance,
)

__all__ = ["TyposquatDetector", "generate_candidates", "edit_distance"]
