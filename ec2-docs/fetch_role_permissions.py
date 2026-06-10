#!/usr/bin/env python3
"""Resolve every role attached to an instance (via its instance profile) and
download the role's permissions: attached managed policy documents + inline
policies. Writes json/role_permissions.json.

Called by fetch_all.cmd. Standalone:
    python fetch_role_permissions.py <json_dir> <region> [profile]
"""
import json
import subprocess
import sys
from pathlib import Path

out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("json")
region = sys.argv[2] if len(sys.argv) > 2 else "us-east-1"
profile = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] else None


def aws(*args):
    cmd = ["aws", *args, "--region", region, "--output", "json"]
    if profile:
        cmd += ["--profile", profile]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip())
    return json.loads(res.stdout or "{}")


def roles_in_use():
    assoc = json.loads((out_dir / "iam_instance_profiles.json").read_text())
    names = set()
    for a in assoc.get("IamInstanceProfileAssociations", []):
        prof = a.get("IamInstanceProfile", {}).get("Arn", "").rsplit("/", 1)[-1]
        if not prof:
            continue
        data = aws("iam", "get-instance-profile", "--instance-profile-name", prof)
        for r in data.get("InstanceProfile", {}).get("Roles", []):
            names.add(r["RoleName"])
    return sorted(names)


def permissions_for(role):
    out = {"AttachedManagedPolicies": [], "InlinePolicies": {}}
    for p in aws("iam", "list-attached-role-policies",
                 "--role-name", role).get("AttachedPolicies", []):
        arn = p["PolicyArn"]
        ver = aws("iam", "get-policy", "--policy-arn", arn)["Policy"]["DefaultVersionId"]
        doc = aws("iam", "get-policy-version", "--policy-arn", arn,
                  "--version-id", ver)["PolicyVersion"]["Document"]
        out["AttachedManagedPolicies"].append(
            {"PolicyName": p["PolicyName"], "PolicyArn": arn, "Document": doc})
    for nm in aws("iam", "list-role-policies",
                  "--role-name", role).get("PolicyNames", []):
        out["InlinePolicies"][nm] = aws(
            "iam", "get-role-policy", "--role-name", role,
            "--policy-name", nm)["PolicyDocument"]
    return out


def main():
    try:
        roles = roles_in_use()
    except FileNotFoundError:
        print("  iam_instance_profiles.json missing - run the ec2 steps first")
        (out_dir / "role_permissions.json").write_text("{}")
        return
    result = {}
    for role in roles:
        print(f"    role: {role}")
        try:
            result[role] = permissions_for(role)
        except RuntimeError as e:
            result[role] = {"error": str(e)}
    (out_dir / "role_permissions.json").write_text(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
