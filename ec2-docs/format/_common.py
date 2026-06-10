"""Shared helpers so each formatter stays short and focused.

Each formatter:
  - reads exactly ONE json file produced by one aws cli command
  - prints a Markdown section to stdout
  - is runnable standalone:  python format_<x>.py [json_dir]
"""
import json
import sys
from pathlib import Path


def json_dir():
    """Folder holding the *.json files (default ./json, override via argv[1])."""
    return Path(sys.argv[1]) if len(sys.argv) > 1 else Path("json")


def load(name):
    """Load <json_dir>/<name>.json, or {} if absent."""
    p = json_dir() / f"{name}.json"
    return json.loads(p.read_text() or "{}") if p.exists() else {}


def table(headers, rows):
    """GitHub-flavored Markdown table. None -> '', pipes/newlines escaped."""
    if not rows:
        return "_None found._"
    def c(x):
        return str(x).replace("|", "\\|").replace("\n", " ") if x is not None else ""
    lines = ["| " + " | ".join(headers) + " |",
             "| " + " | ".join("---" for _ in headers) + " |"]
    lines += ["| " + " | ".join(c(v) for v in r) + " |" for r in rows]
    return "\n".join(lines)


def name_tag(obj):
    """Return the value of the Name tag, or ''."""
    for t in obj.get("Tags", []) or []:
        if t.get("Key") == "Name":
            return t.get("Value")
    return ""


def emit(markdown):
    """Print a section with a trailing blank line."""
    print(markdown.rstrip() + "\n")
