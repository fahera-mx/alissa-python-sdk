# alissa

The `alissa` distribution: the single package that owns and anchors the
`alissa` import namespace, and the curation point for its tool extras.

## The model

This distribution ships **only** the leaf packages `alissa.sdk` and
`alissa.utils`. Everything above them is a
[PEP 420](https://peps.python.org/pep-0420/) namespace package with no
`__init__.py`, so other distributions — pulled in through this package's
extras — contribute their own subtrees under the same namespace:

```
alissa/                                  ← namespace (no __init__.py)
├── sdk/               __init__.py        ← THIS distribution: SDK surface + version file
├── utils/             __init__.py        ← THIS distribution: shared helpers (e.g. utils.version)
└── tools/                               ← namespace (no __init__.py)
    └── github/                          ← namespace
        └── reviewloop/  __init__.py      ← ships from alissa-tools-github-reviewloop
```

The rule (same as every distribution in this ecosystem): own your leaves,
declare only those subtrees (`find_namespace_packages(include=[...])`), and never
add an `__init__.py` at a namespace level — doing so would claim it for one
distribution and shadow the others.

"Owning the namespace" here means being the **anchor**: the distribution you
`pip install`, the one that provides the top-level SDK surface (`alissa.sdk`),
and the one whose extras enumerate the available tools.

## Install

```sh
pip install alissa                          # SDK core only, zero third-party deps
pip install 'alissa[tools.github.revloop]'  # + the GitHub review-loop tool
pip install 'alissa[all]'                   # + every tool extra
```

Each extra pulls in a separately published tool distribution (e.g.
`alissa-tools-github-reviewloop`), which merges its `alissa.tools.*` packages
into the namespace. pip normalizes the dotted extra name, so
`alissa[tools.github.revloop]` resolves.

Extra names are decoupled from distribution names by the curated registry, so
they need not match: `tools.github.revloop` currently pulls
`alissa-tools-github-reviewloop`. That package will be renamed to `revloop`
later (to pair with a planned `devloop`); only the registry changes when it does.

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

## API bindings (`alissa.sdk.api`)

Typed access to the Alissa REST API — stdlib-only, like the rest of the core.
One `ApiClient` owns the base URL, the bearer token, JSON and the error
envelope; each API surface is a binding module on top of it, so there is never a
second HTTP stack in this SDK.

Configuration: `ALISSA_API_TOKEN` (or `token=`) and `ALISSA_BASE` (or
`base_url=`, default `https://api.alissa.app`).

> **On the base-URL variable.** The Node `alissa` CLI spells this knob
> `ALISSA_API_BASE`, not `ALISSA_BASE`. This SDK reads `ALISSA_BASE` first
> (matching its Python siblings) and falls back to `ALISSA_API_BASE`, so
> exporting either one points the CLI *and* the SDK at the same deployment.
> Set both and `ALISSA_BASE` wins.

Requests never follow redirects: the API is a fixed JSON surface with no reason
to issue one, and `urllib` would copy the `Authorization` header onto a
cross-origin `Location`. An unexpected 3xx surfaces as an `ApiError` with code
`HTTP_302` (or whichever status arrived) rather than a silent off-origin call.

### Local Bridge queue mode (`alissa.sdk.api.bridge`)

The `/v1/bridge` executor and job surface: four executor endpoints (register,
list, heartbeat, stop) and seven job endpoints (feed, detail, claim, start,
progress, fulfill, fail).

**Bindings only.** The executor *daemon* — polling, claim state machine, tmux —
is the Node `alissa` CLI's, and none of it lives here. This module is typed
request/response plumbing for observers and tooling.

```python
from alissa.sdk.api import BridgeClient

bridge = BridgeClient()                        # token from $ALISSA_API_TOKEN

# Which machines are registered, and are they alive?
for executor in bridge.list_executors():
    print(executor.executor_id, executor.status, executor.last_heartbeat_at)

# Tail one job's status.
job = bridge.get_job("j57bridge0001")
print(job.spec.title, job.status, f"attempt {job.attempt}/{job.max_attempts}")
print(job.progress_note or job.error or "")
```

Errors are branchable by **code**, never by message text. The queue's four 409s
share one base, because they all mean *re-read the row and retry* rather than
*give up*:

```python
from alissa.sdk.api import RetryAfterReadError, StaleConsumerError

try:
    claim = bridge.claim_job(job_id, executor_id=executor_id,
                             consumer_id=nonce, claim_seq=claim_seq)
except StaleConsumerError:
    pass                       # a newer attempt owns this row — stop
except RetryAfterReadError as err:
    print(err.code, err.observed_status)      # re-poll, do not spin
```

## Shared utilities (`alissa.utils`)

Helpers the SDK factors out so every `alissa.*` distribution reuses one
implementation instead of copying it. Downstream packages may treat these as
stable, public API.

### `alissa.utils.version` — load a distribution's version file

Ship a plain-text `version` file next to your package and load it the same way
the SDK loads its own (`alissa/src/main/alissa/sdk/version.py` is the reference):

```python
import os
from alissa.utils.version import Version

version = Version.load(os.path.dirname(__file__), name="alissa-tools-github-reviewloop")
```

`Version.load` warns and falls back to `0.0.0` when the file is missing;
`Version.from_path` raises instead, when a missing file should be fatal.

To use it, declare the SDK as a dependency: `install_requires=["alissa"]` (pin
`alissa>=<version that introduced the helper you use>`). **There is no
dependency cycle** — base `alissa` requires nothing, tools require base `alissa`,
and the `alissa[tools.*]` extras are a separate, opt-in edge. The only
constraint is release ordering: publish `alissa` before a tool that depends on
that version. And no circular *import*: the SDK core never imports tool code.

## Layout

`src/main` holds the package tree, `src/test` mirrors it as `test_*`. The
distribution version lives in the plain-text `version` file next to the package
it versions (`src/main/alissa/sdk/version`), read by both `setup.py` and
`version.py`.

## Adding a tool extra

1. Ship the tool as its own distribution owning a leaf under `alissa.tools.*`
   (see [`alissa-tools-github-reviewloop`](https://pypi.org/project/alissa-tools-github-reviewloop/)
   for the template). Have it load its version via `alissa.utils.version` and
   declare `install_requires=["alissa"]`.
2. Add one line to `extras_require` in [`setup.py`](./setup.py):
   `"tools.<area>.<name>": ["alissa-tools-<area>-<name>"]`. The `all` extra
   updates itself.
