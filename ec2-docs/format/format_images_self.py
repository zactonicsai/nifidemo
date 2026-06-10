"""Formats: aws ec2 describe-images --owners self  ->  json/images_self.json

AMIs owned by this account (the ones available for you to launch). The AMIs
actually backing instances are in *AMIs In Use*.
"""
from _common import load, table, emit


def _root_gib(img):
    for b in img.get("BlockDeviceMappings", []) or []:
        if b.get("DeviceName") == img.get("RootDeviceName"):
            return (b.get("Ebs") or {}).get("VolumeSize")
    return ""


def main():
    data = load("images_self")
    rows = []
    for m in data.get("Images", []):
        rows.append([
            m.get("ImageId"),
            m.get("Name", ""),
            m.get("State"),
            m.get("Architecture"),
            m.get("PlatformDetails", m.get("Platform", "")),
            m.get("RootDeviceType"),
            _root_gib(m),
            m.get("CreationDate", "")[:10],
        ])
    md = "## AMIs Owned (`describe-images --owners self`)\n\n"
    md += (f"{len(rows)} AMI(s) owned by this account and available to launch. "
           "Join on **AMI ID** with the *Instances* section to see which "
           "instances use each one.\n\n")
    md += table(
        ["AMI ID", "Name", "State", "Arch", "Platform",
         "Root Type", "Root GiB", "Created"],
        rows)
    emit(md)


if __name__ == "__main__":
    main()
