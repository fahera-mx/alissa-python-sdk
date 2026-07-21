"""The shared version loader — the contract downstream alissa.* packages rely on.

These lock the public behaviour of ``alissa.utils.version.Version``: parsing,
the strict vs. tolerant loaders, and the ``alissa.utils`` re-export.
"""
from __future__ import annotations

import pytest

from alissa.utils import Version as ReexportedVersion
from alissa.utils.version import Version


def test_reexported_from_the_utils_package():
    assert ReexportedVersion is Version


def test_from_path_reads_and_parses(tmp_path):
    (tmp_path / "version").write_text("1.2.3\n")

    v = Version.from_path(str(tmp_path), name="demo")

    assert v.name == "demo"
    assert v.value == "1.2.3"
    assert str(v) == "1.2.3"
    assert v.components(as_int=True) == [1, 2, 3]
    assert (v.major, v.minor, v.patch) == (1, 2, 3)


def test_from_path_raises_when_absent(tmp_path):
    with pytest.raises(ValueError):
        Version.from_path(str(tmp_path), name="demo")


def test_load_reads_when_present(tmp_path):
    (tmp_path / "version").write_text("4.5.6")

    v = Version.load(str(tmp_path), name="demo")

    assert (v.name, v.value) == ("demo", "4.5.6")


def test_load_falls_back_and_warns_when_absent(tmp_path):
    with pytest.warns(UserWarning):
        v = Version.load(str(tmp_path), name="demo")

    assert v.value == "0.0.0"
    assert v.name == "demo"


def test_load_honors_a_custom_default(tmp_path):
    with pytest.warns(UserWarning):
        v = Version.load(str(tmp_path), name="demo", default="9.9.9")

    assert v.value == "9.9.9"
