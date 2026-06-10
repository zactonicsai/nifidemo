"""Formats: aws ec2 describe-tags  ->  json/tags.json

All resource tags. Join on Resource ID with whichever section owns that
resource (Instances, Volumes, Subnets, ...).
"""
from _common import load, table, emit


def main():
    data = load("tags")
    rows = []
    for t in data.get("Tags", []):
        rows.append([
            t.get("ResourceType"),
            t.get("ResourceId"),
            t.get("Key"),
            t.get("Value"),
        ])
    rows.sort(key=lambda x: (x[0] or "", x[1] or ""))
    md = "## Tags (`describe-tags`)\n\n"
    md += ("Every tag in the region. Join on **Resource ID** with the relevant "
           "section (instance, volume, subnet, etc.).\n\n")
    md += table(["Resource Type", "Resource ID", "Key", "Value"], rows)
    emit(md)


if __name__ == "__main__":
    main()
