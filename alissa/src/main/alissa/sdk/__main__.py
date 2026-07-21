"""Console entry point for the Alissa Python SDK (``alissa-sdk``).

Named ``alissa-sdk`` — not ``alissa`` — on purpose: the ``alissa`` command is
the Alissa by Fahera CLI (tasks, sessions, tmux queues), a separate tool this
SDK does not shadow.
"""
import argparse

from . import __version__, installed_tools


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="alissa-sdk",
        description="Alissa Python SDK — anchors the 'alissa' namespace and its tool extras.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"alissa {__version__}",
    )
    parser.add_argument(
        "--tools",
        action="store_true",
        help="list the alissa.tools.* packages installed in this environment",
    )
    args = parser.parse_args()

    if args.tools:
        tools = installed_tools()
        if tools:
            for name in tools:
                print(name)
        else:
            print("no alissa.tools.* packages installed")
            print("try: pip install 'alissa[tools.github.reviewloop]'")
        return

    print(f"alissa {__version__}")
    print("the Alissa Python SDK — anchors the 'alissa' namespace")
    print("install tools via extras, e.g.: pip install 'alissa[tools.github.reviewloop]'")
    print("list installed tools: alissa-sdk --tools")


if __name__ == "__main__":
    main()
