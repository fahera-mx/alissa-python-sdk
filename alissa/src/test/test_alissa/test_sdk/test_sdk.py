"""The SDK's package contract: version wiring and curated-tool discovery.

These lock the two things the aggregator model depends on — that the leaf
package reports a coherent version, and that tool discovery is driven by the
curated registry through the import machinery (so it is correct for both wheel
and editable installs), without depending on which tools happen to be installed.
"""
from __future__ import annotations

from alissa.sdk import __version__, installed_tools
from alissa.sdk.version import version


def test_version_matches_the_version_file():
    assert __version__ == version.value
    assert version.name == "alissa"


def test_version_is_semver():
    major, minor, patch = version.components(as_int=True)
    assert isinstance(major, int) and isinstance(minor, int) and isinstance(patch, int)


def test_curated_registry_is_wellformed():
    from alissa.sdk._tools import CURATED_TOOLS

    for extra, value in CURATED_TOOLS.items():
        distribution, module = value
        assert extra.startswith("tools."), extra
        assert distribution.startswith("alissa-"), distribution
        assert module.startswith("alissa.tools."), module


def test_installed_tools_returns_a_sorted_subset_of_the_registry():
    from alissa.sdk._tools import CURATED_TOOLS

    curated_modules = {module for _distribution, module in CURATED_TOOLS.values()}
    tools = installed_tools()

    assert isinstance(tools, list)
    assert tools == sorted(tools)
    # Whatever is reported is a curated module — never something invented.
    assert set(tools) <= curated_modules


def test_installed_tools_probes_via_the_import_machinery(monkeypatch):
    # Drive discovery off a fake registry: one importable module, one not.
    # This is deterministic regardless of which real tools are installed.
    import alissa.sdk._tools as tools_module

    monkeypatch.setattr(
        tools_module,
        "CURATED_TOOLS",
        {
            "tools.present": ("alissa-tools-present", "json"),
            "tools.absent": ("alissa-tools-absent", "alissa.tools.__does_not_exist__"),
        },
    )

    result = installed_tools()
    assert "json" in result
    assert "alissa.tools.__does_not_exist__" not in result
