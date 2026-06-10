"""Formats: aws ec2 describe-security-group-rules
            ->  json/security_group_rules.json

The actual ingress/egress permissions, one row per rule. Join on Group ID with
the *Security Groups* section.
"""
from _common import load, table, emit


def _ports(r):
    f, t = r.get("FromPort"), r.get("ToPort")
    if f in (None, -1) and t in (None, -1):
        return "all"
    return str(f) if f == t else f"{f}-{t}"


def _peer(r):
    return (r.get("CidrIpv4") or r.get("CidrIpv6")
            or (r.get("ReferencedGroupInfo") or {}).get("GroupId")
            or r.get("PrefixListId") or "")


def main():
    data = load("security_group_rules")
    rows = []
    for r in data.get("SecurityGroupRules", []):
        proto = r.get("IpProtocol")
        rows.append([
            r.get("GroupId"),
            "egress" if r.get("IsEgress") else "ingress",
            "all" if proto == "-1" else proto,
            _ports(r),
            _peer(r),
            r.get("Description", ""),
        ])
    rows.sort(key=lambda x: (x[0], x[1]))
    md = "## Security Group Rules / Permissions (`describe-security-group-rules`)\n\n"
    md += ("Every ingress and egress rule across all groups. **Source / Dest** "
           "is a CIDR, another security group ID, or a prefix list. Join on "
           "**Group ID** with the *Security Groups* section.\n\n")
    md += table(
        ["Group ID", "Direction", "Protocol", "Ports",
         "Source / Dest", "Description"],
        rows)
    emit(md)


if __name__ == "__main__":
    main()
