"""Formats: aws ec2 describe-volumes  ->  json/volumes.json

EBS volumes with size, type, IOPS and encryption, plus the instance/device
they attach to. Join on Instance ID with the *Instances* section.
"""
from _common import load, table, emit


def main():
    data = load("volumes")
    rows = []
    for v in data.get("Volumes", []):
        for a in (v.get("Attachments") or [{}]):
            rows.append([
                v.get("VolumeId"),
                a.get("InstanceId", "(unattached)"),
                a.get("Device", ""),
                v.get("VolumeType"),
                v.get("Size"),
                v.get("Iops", ""),
                "yes" if v.get("Encrypted") else "no",
                v.get("State"),
            ])
    md = "## Storage (`describe-volumes`)\n\n"
    md += ("EBS volumes, including encryption status, and the instance + device "
           "each is attached to. Join on **Instance ID** with the *Instances* "
           "section.\n\n")
    md += table(
        ["Volume ID", "Instance", "Device", "Type",
         "Size GiB", "IOPS", "Encrypted", "State"],
        rows)
    emit(md)


if __name__ == "__main__":
    main()
