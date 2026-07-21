"""The alissa distribution's version, loaded via the shared utility.

This is the canonical example of the pattern every alissa.* distribution
follows — see :mod:`alissa.utils.version`.
"""
import os

from alissa.utils.version import Version

version = Version.load(os.path.dirname(__file__), name="alissa")
