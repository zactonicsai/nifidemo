"""Formats: aws ec2 describe-vpcs  ->  json/vpcs.json

VPC inventory. Join on VPC ID with Subnets, Networking, Security Groups and
Instances.
"""
from _common import load, table, name_tag, emit


def main():
    data = load("vpcs")
    rows = []
    for v in data.get("Vpcs", []):
        rows.append([
            v.get("VpcId"),
            name_tag(v),
            v.get("CidrBlock"),
            v.get("State"),
            "yes" if v.get("IsDefault") else "no",
            v.get("InstanceTenancy"),
        ])
    md = "## VPCs (`describe-vpcs`)\n\n"
    md += ("Virtual networks. Join on **VPC ID** with *Subnets*, *Networking*, "
           "*Security Groups* and *Instances*.\n\n")
    md += table(
        ["VPC ID", "Name", "CIDR", "State", "Default", "Tenancy"],
        rows)
    emit(md)


if __name__ == "__main__":
    main()
