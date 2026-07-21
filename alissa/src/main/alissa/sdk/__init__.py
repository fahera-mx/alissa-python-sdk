"""alissa — the Alissa Python SDK.

This distribution is the canonical anchor of the ``alissa`` import namespace.
It ships **no** ``__init__.py`` at the namespace levels (``alissa``,
``alissa.tools``, ...) — only this owned leaf, ``alissa.sdk``, is a regular
package. That keeps every namespace level a
`PEP 420 <https://peps.python.org/pep-0420/>`_ implicit namespace package, so
tool distributions pulled in through extras — for example
``pip install 'alissa[tools.github.reviewloop]'`` — merge their own
``alissa.tools.*`` subtrees into the same namespace at import time.

The SDK's own surface lives here, under ``alissa.sdk``. Tools live under
``alissa.tools.*`` and are discovered dynamically via :func:`installed_tools`.
"""

from .version import version

__all__ = ["version", "__version__", "installed_tools"]
__version__ = version.value


def installed_tools() -> list:
    """Return the curated ``alissa.tools.*`` packages installed in this env.

    The SDK curates a set of tools, each pulled in by an extra
    (``pip install 'alissa[<extra>]'``); see :data:`alissa.sdk._tools.CURATED_TOOLS`,
    the same registry ``setup.py`` builds ``extras_require`` from. This probes
    each curated tool with :func:`importlib.util.find_spec`, which resolves
    through the import machinery — so it works for both wheel and editable
    installs (a plain filesystem walk of ``__path__`` misses editable ones,
    whose path entries are synthetic finder hooks). Returns an empty list when
    no tool extras are installed.
    """
    import importlib.util

    from ._tools import CURATED_TOOLS

    found: list = []
    for _extra, (_distribution, module) in CURATED_TOOLS.items():
        try:
            spec = importlib.util.find_spec(module)
        except (ImportError, ValueError):
            # A broken parent package must not sink discovery of the others.
            spec = None
        if spec is not None:
            found.append(module)

    return sorted(found)
