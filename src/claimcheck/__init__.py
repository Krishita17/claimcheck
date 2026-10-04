"""ClaimCheck — a defensive dependency-confusion exposure checker.

ClaimCheck reads an organization's internal dependency names from manifests,
lockfiles, registry-scope configs, CI files, and Dockerfiles, then checks each
name against the public PyPI and npm registries to answer the only question
that matters for dependency confusion: could an attacker claim this name?

The tool is strictly read-only against registries. It never publishes,
registers, reserves, or squats any package name. The deliverable is a report.

Author: Krishita Sanjay Choksi
License: MIT
"""

__version__ = "0.1.0"
__author__ = "Krishita Sanjay Choksi"

__all__ = ["__version__", "__author__"]
