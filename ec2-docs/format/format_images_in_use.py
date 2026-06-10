"""Formats: aws ec2 describe-images --image-ids <ids in use>
            ->  json/images_in_use.json

AMIs that current instances were launched from (may be owned by Amazon or the
Marketplace). Guarantees the instance -> AMI relationship has no gaps.
"""
from _common import load, table, emit


def _root_gib(img):
    for b in img.get("BlockDeviceMappings", []) or []:
        if b.get("DeviceName") == img.get("RootDeviceName"):
            return (b.get("Ebs") or {}).get("VolumeSize")
    return ""


def main():
    data = load("images_in_use")
    rows = []
    for m in data.get("Images", []):
        rows.append([
            m.get("ImageId"),
            m.get("Name", ""),
            m.get("OwnerId"),
            m.get("Architecture"),
            m.get("PlatformDetails", m.get("Platform", "")),
            m.get("RootDeviceType"),
            _root_gib(m),
            "yes" if m.get("Public") else "no",
        ])
    md = "## AMIs In Use (`describe-images --image-ids ...`)\n\n"
    md += (f"{len(rows)} AMI(s) referenced by running/stopped instances, including "
           "those owned by Amazon or the Marketplace. Join on **AMI ID** with the "
           "*Instances* section.\n\n")
    md += table(
        ["AMI ID", "Name", "Owner", "Arch", "Platform",
         "Root Type", "Root GiB", "Public"],
        rows)
    emit(md)


if __name__ == "__main__":
    main()
