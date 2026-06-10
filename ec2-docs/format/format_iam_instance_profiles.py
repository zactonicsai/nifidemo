"""Formats: aws ec2 describe-iam-instance-profile-associations
            ->  json/iam_instance_profiles.json

The instance -> instance-profile -> IAM role relationship. Permissions for the
roles themselves are in the *Role Permissions* section.
"""
from _common import load, table, emit


def main():
    data = load("iam_instance_profiles")
    rows = []
    for a in data.get("IamInstanceProfileAssociations", []):
        arn = a.get("IamInstanceProfile", {}).get("Arn", "")
        rows.append([
            a.get("InstanceId"),
            arn.rsplit("/", 1)[-1],   # instance-profile name (== role name typically)
            a.get("State"),
            a.get("AssociationId"),
            arn,
        ])
    md = "## IAM Roles (`describe-iam-instance-profile-associations`)\n\n"
    md += ("Which IAM instance profile (and therefore role) each instance runs "
           "as. One profile per instance; one role per profile. The actual "
           "permissions are in the *Role Permissions* section, joined by role "
           "name.\n\n")
    md += table(
        ["Instance ID", "Profile / Role", "State",
         "Association ID", "Profile ARN"],
        rows)
    emit(md)


if __name__ == "__main__":
    main()
