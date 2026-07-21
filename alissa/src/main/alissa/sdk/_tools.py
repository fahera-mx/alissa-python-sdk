"""Single source of truth for the tools this SDK curates.

Each entry maps a pip *extra* name to the distribution it pulls in and the
module that distribution makes importable:

    "<extra>": ("<distribution>", "<module>")

`setup.py` reads this to build ``extras_require`` (so the extras and the
runtime never drift), and :func:`alissa.sdk.installed_tools` reads it to report
which curated tools are actually installed.

To curate a new tool, add one line here — nothing else needs editing.
"""

CURATED_TOOLS = {
    "tools.github.reviewloop": (
        "alissa-tools-github-reviewloop",
        "alissa.tools.github.reviewloop",
    ),
}
