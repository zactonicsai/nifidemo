"""Formats: aws ec2 describe-security-groups  ->  json/security_groups.json

Security group inventory (the groups themselves). The per-rule permissions are
in *Security Group Rules*; instance attachments are in *Instances*.
"""
from _common import load, table, emit


def main():
    data = load("security_groups")
    rows = []
    for g in data.get("SecurityGroups", []):
        rows.append([
            g.get("GroupId"),
            g.get("GroupName"),
            g.get("VpcId"),
            len(g.get("IpPermissions", []) or []),
            len(g.get("IpPermissionsEgress", []) or []),
            g.get("Description"),
        ])
    md = "## Security Groups (`describe-security-groups`)\n\n"
    md += ("Inventory of all security groups with rule counts. Individual rules "
           "(the actual permissions) are expanded in *Security Group Rules*; "
           "which instances use each group is in the *Instances* section.\n\n")
    md += table(
        ["Group ID", "Group Name", "VPC",
         "Ingress Rules", "Egress Rules", "Description"],
        rows)
    emit(md)


if __name__ == "__main__":
    main()
