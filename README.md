# alissa-python-sdk

The single Python package that owns and anchors the `alissa` import namespace —
`import alissa.sdk` — and curates its **tool extras**:

```sh
pip install alissa                               # SDK core, zero third-party deps
pip install 'alissa[tools.github.reviewloop]'    # + a tool, merged into alissa.tools.*
pip install 'alissa[all]'                        # + every tool
```

## How ownership works

`alissa` is the anchor distribution: the thing you `pip install`, the top-level
SDK surface (`alissa.sdk`), and the list of available tools (its extras). But it
ships **no** `__init__.py` at the namespace levels, so it doesn't monopolize the
namespace — tool distributions pulled in by extras merge their own
`alissa.tools.*` subtrees in via [PEP 420](https://peps.python.org/pep-0420/):

```
alissa/                                  ← namespace (no __init__.py)
├── sdk/               __init__.py        ← the SDK distribution: surface + version file
├── utils/             __init__.py        ← the SDK distribution: shared helpers (utils.version)
└── tools/                               ← namespace
    └── github/
        └── reviewloop/  __init__.py      ← ships from alissa-tools-github-reviewloop
```

Each `alissa[tools.<area>.<name>]` extra maps to a separately published
distribution (`alissa-tools-<area>-<name>`). Tools stay independently versioned
and released; the SDK just curates which ones exist and pulls them in on demand.
See [`alissa/README.md`](./alissa/README.md) for the full model and for how to
add a new tool extra.

## Repository layout

This repo is a monorepo of distributions. Today it holds one, `alissa/`; the
shared dev tooling and CI live at the root and matrix over each distribution's
directory name.

```
alissa-python-sdk/
├── alissa/                     ← the `alissa` distribution
│   ├── setup.py                ← packaging + extras_require (the tool curation)
│   ├── requirements.txt        ← core deps (empty — the SDK core has none)
│   ├── MANIFEST.in
│   └── src/
│       ├── main/alissa/sdk/    ← owned leaf: SDK surface (+ plain-text `version` file)
│       ├── main/alissa/utils/  ← owned leaf: shared helpers (alissa.utils.version)
│       └── test/test_alissa/   ← mirrors main as test_*
├── .github/workflows/          ← style / types / tests / wheel / publish (matrix: alissa)
├── check-style.sh  check-types.sh  tests-unit.sh  tests-coverage.sh
├── requirements-develop.txt
└── .python-version             ← 3.12.3
```

## Develop

```sh
python -m venv venv && source venv/bin/activate
pip install -r requirements-develop.txt
pip install -e ./alissa

alissa-py                  # SDK version + how to add tools
alissa-py --tools          # list installed alissa.tools.* packages
```

## Checks

Each script takes a distribution directory (matching the CI matrix):

```sh
bash tests-unit.sh alissa
bash tests-coverage.sh alissa
bash check-style.sh alissa
bash check-types.sh alissa
```

## Publishing

Publishing is driven by the per-distribution `version` file
(`alissa/src/main/alissa/sdk/version`). Merging a PR to `main` that bumps it
publishes to PyPI; a PR that doesn't bump it publishes nothing
(`twine upload --skip-existing`). Versions are irreversible once on PyPI.
