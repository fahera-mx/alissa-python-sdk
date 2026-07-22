"""Load a distribution's version from its plain-text ``version`` file.

Factored out so every ``alissa.*`` distribution reads its version identically
instead of re-implementing the loader. Ship a plain-text ``version`` file next
to your package and, in a ``version.py`` beside it:

    import os
    from alissa.utils.version import Version

    version = Version.load(os.path.dirname(__file__), name="my-distribution")

:meth:`Version.load` tolerates a missing file (warns, falls back to a default);
:meth:`Version.from_path` raises instead, when a missing file should be fatal.

Downstream packages may treat this as stable, public API — declare ``alissa`` as
a dependency (``install_requires=["alissa"]``) to guarantee it is importable.
"""
import os
import warnings
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Version:
    name: str
    value: str

    def components(self, as_int: bool = False) -> list:
        return [int(val) if as_int else val for val in self.value.split(".")]

    @property
    def major(self) -> int:
        component, *_ = self.components(as_int=True)
        return component

    @property
    def minor(self) -> int:
        _, component, *_ = self.components(as_int=True)
        return component

    @property
    def patch(self) -> int:
        *_, component = self.components(as_int=True)
        return component

    def __str__(self) -> str:
        return self.value

    @classmethod
    def from_path(cls, dirpath: str, name: str) -> "Version":
        """Read the version from the ``*version`` file in ``dirpath``.

        Raises ``ValueError`` when no such file exists.
        """
        for file in os.listdir(dirpath):
            if file.lower().endswith("version"):
                filepath = os.path.join(dirpath, file)
                break
        else:
            raise ValueError("Version file not found for package name: " + name)

        with open(filepath, "r") as version_file:
            return cls(name=name, value=version_file.readline().strip())

    @classmethod
    def load(cls, dirpath: str, name: str, default: str = "0.0.0") -> "Version":
        """Like :meth:`from_path`, but warn and fall back to ``default`` if absent."""
        try:
            return cls.from_path(dirpath, name)
        except Exception:
            warnings.warn(
                f"Version file not found for package name: {name}, using {default}",
                stacklevel=2,
            )
            return cls(name=name, value=default)
