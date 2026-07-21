# alissa

The `alissa` distribution: the single package that owns and anchors the
`alissa` import namespace, and the curation point for its tool extras.

## The model

This distribution ships **only** the leaf package `alissa.sdk`. Everything
above it is a [PEP 420](https://peps.python.org/pep-0420/) namespace package
with no `__init__.py`, so other distributions — pulled in through this package's
extras — contribute their own subtrees under the same namespace:

```
alissa/                                  ← namespace (no __init__.py)
├── sdk/               __init__.py        ← THIS distribution owns this leaf
└── tools/                               ← namespace (no __init__.py)
    └── github/                          ← namespace
        └── reviewloop/  __init__.py      ← ships from alissa-tools-github-reviewloop
```

The rule (same as every distribution in this ecosystem): own a leaf, declare
only that subtree (`find_namespace_packages(include=[PACKAGE, f"{PACKAGE}.*"])`),
and never add an `__init__.py` at a namespace level — doing so would claim it for
one distribution and shadow the others.

"Owning the namespace" here means being the **anchor**: the distribution you
`pip install`, the one that provides the top-level SDK surface (`alissa.sdk`),
and the one whose extras enumerate the available tools.

## Install

```sh
pip install alissa                        # SDK core only, zero third-party deps
pip install 'alissa[tools.github.reviewloop]'   # + the GitHub review-loop tool
pip install 'alissa[all]'                 # + every tool extra
```

Each extra pulls in a separately published tool distribution (e.g.
`alissa-tools-github-reviewloop`), which merges its `alissa.tools.*` packages
into the namespace. pip normalizes the dotted extra name, so
`alissa[tools.github.reviewloop]` resolves.

### Editable / development install

```sh
pip install -e ./alissa
```

## Console scripts

| Command | Entry point |
| --- | --- |
| `alissa-py` | `alissa.sdk.__main__:main` |

The command is `alissa-py` — deliberately **not** `alissa`, which is the Alissa
by Fahera CLI this SDK does not shadow. The `-py` suffix marks it, explicitly,
as the Python SDK's counterpart. (A literal `alissa.py` can't be used: the
console-script file `bin/alissa.py` would shadow the importable `alissa`
package.)

```sh
alissa-py              # SDK version + how to add tools
alissa-py --tools      # list installed alissa.tools.* packages
alissa-py --version
```

## Using it

```python
from alissa.sdk import __version__, installed_tools

print(__version__)
print(installed_tools())   # ['alissa.tools.github.reviewloop', ...] — whatever extras are installed
```

`installed_tools()` reports which of the SDK's curated tools are installed,
probing each through the import machinery — so it is correct for both wheel and
editable installs. The curated set lives in `src/main/alissa/sdk/_tools.py`, the
same registry `setup.py` builds the extras from.

## Layout

`src/main` holds the package tree, `src/test` mirrors it as `test_*`. The
distribution version lives in the plain-text `version` file next to the package
it versions (`src/main/alissa/sdk/version`), read by both `setup.py` and
`version.py`.

## Adding a tool extra

1. Ship the tool as its own distribution owning a leaf under `alissa.tools.*`
   (see [`alissa-tools-github-reviewloop`](https://pypi.org/project/alissa-tools-github-reviewloop/)
   for the template).
2. Add one line to `extras_require` in [`setup.py`](./setup.py):
   `"tools.<area>.<name>": ["alissa-tools-<area>-<name>"]`. The `all` extra
   updates itself.
