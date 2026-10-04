"""Name extraction and normalization."""

from .normalize import (
    canonicalize_pypi,
    canonicalize_npm,
    split_npm_scope,
    make_name,
    merge_names,
)

__all__ = [
    "canonicalize_pypi",
    "canonicalize_npm",
    "split_npm_scope",
    "make_name",
    "merge_names",
]
