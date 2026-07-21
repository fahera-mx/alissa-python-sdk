import os
from setuptools import setup, find_namespace_packages


CODEBASE_PATH = os.environ.get(
    "CODEBASE_PATH",
    default=os.path.join("src", "main"),
)

# This distribution owns exactly ONE leaf package, `alissa.sdk`. Everything
# above it (`alissa`, `alissa.tools`, ...) is left as a PEP 420 namespace with
# no __init__.py, so tool distributions installed through the extras below merge
# their own alissa.tools.* subtrees into the same namespace. Adding an
# __init__.py at any namespace level would claim it for this distribution and
# shadow the tools.
PACKAGE = "alissa.sdk"

with open("requirements.txt", "r") as file:
    requirements = [line for line in file.read().splitlines() if line and not line.startswith("#")]

version_filepath = os.path.join(CODEBASE_PATH, *PACKAGE.split("."), "version")
with open(version_filepath, "r") as file:
    version = file.read().strip()


with open("README.md") as file:
    readme = file.read()


# Extras are the SDK's curation surface. Each extra pulls in a separately
# published tool distribution that contributes its own alissa.tools.* subtree;
# the SDK core itself carries no third-party dependencies. Install one with
#   pip install 'alissa[tools.github.reviewloop]'
# pip normalizes the dotted extra name, so the dotted spelling above resolves.
#
# The curated tools live in the package's `_tools.py` so the extras and the
# runtime's installed_tools() share one source of truth. Read it here without
# importing the package (its deps may not be installed at build time).
_tools_namespace: dict = {}
_tools_filepath = os.path.join(CODEBASE_PATH, *PACKAGE.split("."), "_tools.py")
with open(_tools_filepath, "r") as file:
    exec(compile(file.read(), _tools_filepath, "exec"), _tools_namespace)

extras_require = {
    extra: [distribution]
    for extra, (distribution, _module) in _tools_namespace["CURATED_TOOLS"].items()
}
# `all` is the union of every tool extra, kept in sync automatically.
extras_require["all"] = sorted({dep for deps in extras_require.values() for dep in deps})


setup(
    name="alissa",
    version=version,
    description="Alissa Python SDK — anchors the 'alissa' namespace and its tool extras.",
    long_description=readme,
    long_description_content_type='text/markdown',
    url="https://alissa.app",
    author="Fahera",
    author_email="support@alissa.app",
    packages=find_namespace_packages(
        where=CODEBASE_PATH,
        include=[PACKAGE, f"{PACKAGE}.*"],
    ),
    package_dir={
        "": CODEBASE_PATH
    },
    package_data={
        "": [
            version_filepath,
        ]
    },
    entry_points={
        "console_scripts": [
            "alissa-sdk=alissa.sdk.__main__:main",
        ]
    },
    install_requires=requirements,
    extras_require=extras_require,
    include_package_data=True,
    python_requires=">=3.11",
)
