"""Formats: json/role_permissions.json (produced by fetch_role_permissions.py,
which wraps `aws iam get/list-*-role-policies`).

Full IAM permissions for each role attached to an instance: managed policy
documents + inline policies. Join on role name with the *IAM Roles* section.
"""
import json
from _common import load, emit


def main():
    perms = load("role_permissions")
    md = "## Role Permissions (`iam get/list-*-role-policies`)\n\n"
    if not perms:
        emit(md + "_No role permissions collected._")
        return
    md += ("Effective permissions for every role used by an instance profile. "
           "Join on **role name** with the *IAM Roles* section.\n\n")
    for role, entry in perms.items():
        md += f"### Role: `{role}`\n\n"
        if "error" in entry:
            md += f"> Could not read: {entry['error']}\n\n"
            continue
        managed = entry.get("AttachedManagedPolicies", [])
        md += "**Managed policies:** "
        md += (", ".join(f"`{p['PolicyName']}`" for p in managed) or "_none_") + "\n\n"
        for p in managed:
            md += f"<details><summary>{p['PolicyName']} (managed)</summary>\n\n"
            md += "```json\n" + json.dumps(p["Document"], indent=2) + "\n```\n\n</details>\n\n"
        inline = entry.get("InlinePolicies", {})
        if inline:
            md += "**Inline policies:**\n\n"
            for nm, doc in inline.items():
                md += f"<details><summary>{nm} (inline)</summary>\n\n"
                md += "```json\n" + json.dumps(doc, indent=2) + "\n```\n\n</details>\n\n"
    emit(md)


if __name__ == "__main__":
    main()
