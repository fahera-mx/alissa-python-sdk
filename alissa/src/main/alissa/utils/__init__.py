"""alissa.utils — shared helpers for the ``alissa.*`` ecosystem.

The SDK factors these out so every ``alissa.*`` distribution (tools included)
reuses one implementation instead of copying it. Downstream packages may assume
``alissa`` is importable at runtime and should declare it as a dependency
(``install_requires=["alissa"]``); there is no dependency cycle, because the SDK
core never imports tool code.
"""
from .version import Version

__all__ = ["Version"]
