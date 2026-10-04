"""Exposure report generation (text, markdown, JSON, SARIF)."""

from .report import (
    render_text,
    render_markdown,
    render_json,
    verdict_counts,
)
from .sarif import render_sarif

__all__ = [
    "render_text",
    "render_markdown",
    "render_json",
    "render_sarif",
    "verdict_counts",
]
