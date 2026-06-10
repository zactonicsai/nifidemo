"""Formats: aws ec2 describe-subnets  ->  json/subnets.json

Subnet inventory. Join on Subnet ID with Instances / Networking, and on VPC ID
with the *VPCs* section.
"""
from _common import load, table, name_tag, emit


def main():
    data = load("subnets")
    rows = []
    for s in data.get("Subnets", []):
        rows.append([
            s.get("SubnetId"),
            name_tag(s),
            s.get("VpcId"),
            s.get("CidrBlock"),
            s.get("AvailabilityZone"),
            s.get("AvailableIpAddressCount"),
            "yes" if s.get("MapPublicIpOnLaunch") else "no",
        ])
    md = "## Subnets (`describe-subnets`)\n\n"
    md += ("Subnets with CIDR, AZ and auto-public-IP behavior. Join on **Subnet "
           "ID** with *Instances*/*Networking*, and on **VPC** with the *VPCs* "
           "section.\n\n")
    md += table(
        ["Subnet ID", "Name", "VPC", "CIDR", "AZ",
         "Free IPs", "Auto Public IP"],
        rows)
    emit(md)


if __name__ == "__main__":
    main()
