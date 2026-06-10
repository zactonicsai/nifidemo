#!/usr/bin/env python3
"""Assemble EC2_DOCUMENTATION.md by running every format_*.py in order and
capturing its stdout. Each formatter is independent and one-command-focused;
this just stitches them together with a header and TOC.

    python build_docs.py [json_dir] [output.md]

Defaults: json_dir = ./json, output = ./EC2_DOCUMENTATION.md
"""
import datetime
import io
import importlib.util
import sys
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
FMT = HERE / "format"

# Order of sections in the final document.
ORDER = [
    "format_instances",
    "format_instance_status",
    "format_metadata",
    "format_iam_instance_profiles",
    "format_role_permissions",
    "format_security_groups",
    "format_security_group_rules",
    "format_networking",          # describe-network-interfaces
    "format_volumes",
    "format_subnets",
    "format_vpcs",
    "format_key_pairs",
    "format_tags",
    "format_images_self",
    "format_images_in_use",
]

# map module -> filename (networking module file is format_network_interfaces.py)
FILES = {m: m for m in ORDER}
FILES["format_networking"] = "format_network_interfaces"


def run_formatter(mod_name, json_dir):
    """Import a formatter by path, call main() with argv set to json_dir,
    capture its printed Markdown."""
    file = FMT / (FILES[mod_name] + ".py")
    spec = importlib.util.spec_from_file_location(mod_name, file)
    module = importlib.util.module_from_spec(spec)
    sys.argv = ["", str(json_dir)]          # formatters read argv[1]
    sys.path.insert(0, str(FMT))            # so `import _common` works
    buf = io.StringIO()
    with redirect_stdout(buf):
        spec.loader.exec_module(module)
        module.main()
    return buf.getvalue()


def toc_entry(section_md):
    for line in section_md.splitlines():
        if line.startswith("## "):
            title = line[3:].strip()
            anchor = title.lower()
            for ch in "()`/.\u2192*":
                anchor = anchor.replace(ch, "")
            anchor = "-".join(anchor.split())
            return f"- [{title}](#{anchor})", title
    return None, None


def main():
    json_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "json"
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE / "EC2_DOCUMENTATION.md"
    if not json_dir.exists():
        sys.exit(f"JSON folder not found: {json_dir}\nRun fetch_all.cmd first.")

    sections, toc = [], []
    for mod in ORDER:
        md = run_formatter(mod, json_dir)
        sections.append(md)
        entry, _ = toc_entry(md)
        if entry:
            toc.append(entry)

    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    head = ("# EC2 Configuration & Relationships\n\n"
            f"_Generated {now} from AWS CLI JSON in `{json_dir}`._\n\n"
            "## Contents\n\n" + "\n".join(toc) + "\n\n")
    out.write_text(head + "\n".join(sections))
    print(f"Wrote {out}  ({out.stat().st_size:,} bytes, {len(ORDER)} sections)")


if __name__ == "__main__":
    main()
