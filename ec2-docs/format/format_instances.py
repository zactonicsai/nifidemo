"""Formats: aws ec2 describe-instances  ->  json/instances.json

Core instance configuration. Relates each instance to its AMI (read_amis),
IAM role (iam profiles), security groups, subnet/VPC and key pair.
"""
from _common import load, table, name_tag, emit


def main():
    data = load("instances")
    rows = []
    for r in data.get("Reservations", []):
        for i in r.get("Instances", []):
            rows.append([
                i.get("InstanceId"),
                name_tag(i),
                i.get("InstanceType"),
                i.get("State", {}).get("Name"),
                i.get("ImageId"),
                i.get("Placement", {}).get("AvailabilityZone"),
                i.get("VpcId"),
                i.get("SubnetId"),
                i.get("KeyName"),
                i.get("LaunchTime", "")[:19],
            ])
    md = "## Instances (`describe-instances`)\n\n"
    md += ("Core configuration of every instance. The **AMI** column links to "
           "the *AMIs* section; **VPC/Subnet** to *Networking*; **Key** to "
           "*Key Pairs*; the instance's role is in *IAM Roles*.\n\n")
    md += table(
        ["Instance ID", "Name", "Type", "State", "AMI", "AZ",
         "VPC", "Subnet", "Key", "Launched"],
        rows)
    emit(md)


if __name__ == "__main__":
    main()
