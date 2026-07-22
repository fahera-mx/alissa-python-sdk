"""Single source of truth for the tools this SDK curates.

Each entry maps a pip *extra* name to the distribution it pulls in and the
module that distribution makes importable:

    "<extra>": ("<distribution>", "<module>")

`setup.py` reads this to build ``extras_require`` (so the extras and the
runtime never drift), and :func:`alissa.sdk.installed_tools` reads it to report
which curated tools are actually installed.

To curate a new tool, add one line here — nothing else needs editing.

Note the indirection is deliberate: the public extra name is decoupled from the
distribution and module names, so a tool can be renamed on the SDK side before
(or independently of) its source package.
"""

CURATED_TOOLS = {
    # The extra is `revloop`; the distribution and module are still `reviewloop`
    # because that is what is published on PyPI. The source package will be
    # renamed to `revloop` later — to pair with a planned `devloop` — and the
    # two values below move with it then. Renaming them before the rename ships
    # would resolve to a distribution that does not exist.
    "tools.github.revloop": (
        "alissa-tools-github-reviewloop",
        "alissa.tools.github.reviewloop",
    ),
}
