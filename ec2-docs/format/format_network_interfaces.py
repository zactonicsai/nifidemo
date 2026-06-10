"""Formats: aws ec2 describe-network-interfaces
            ->  json/network_interfaces.json

ENIs with their IPs, subnet/VPC and the instance they attach to. Join on the
attached Instance ID with the *Instances* section.
"""
from _common import load, table, emit


def main():
    data = load("network_interfaces")
    rows = []
    for ni in data.get("NetworkInterfaces", []):
        att = ni.get("Attachment") or {}
        rows.append([
            ni.get("NetworkInterfaceId"),
            att.get("InstanceId", "(unattached)"),
            ni.get("PrivateIpAddress"),
            (ni.get("Association") or {}).get("PublicIp", ""),
            ni.get("SubnetId"),
            ni.get("VpcId"),
            ni.get("Status"),
        ])
    md = "## Networking (`describe-network-interfaces`)\n\n"
    md += ("Network interfaces, their private/public IPs and subnet/VPC "
           "placement. Join on **Instance ID** with the *Instances* section.\n\n")
    md += table(
        ["ENI ID", "Instance", "Private IP", "Public IP",
         "Subnet", "VPC", "Status"],
        rows)
    emit(md)


if __name__ == "__main__":
    main()
