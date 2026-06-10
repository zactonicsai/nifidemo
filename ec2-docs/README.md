# EC2 Docs (Windows)

Each AWS CLI command is paired with one short, focused Python formatter. The CLI
command writes a JSON file; its formatter turns that one file into a Markdown
section that explains the fields and how they relate to other sections.

Verified against **AWS CLI v2.34.x** on **Windows** (cmd.exe).

## How it fits together

```
fetch_all.cmd               # runs every aws cli command -> json\*.json (Windows)
fetch_role_permissions.py   # chained iam calls -> json\role_permissions.json
build_docs.py               # runs all formatters -> EC2_DOCUMENTATION.md
format\
  _common.py                # tiny shared helpers (load json, md table)
  format_instances.py
  format_instance_status.py
  format_metadata.py
  format_iam_instance_profiles.py
  format_role_permissions.py
  format_security_groups.py
  format_security_group_rules.py
  format_network_interfaces.py
  format_volumes.py
  format_subnets.py
  format_vpcs.py
  format_key_pairs.py
  format_tags.py
  format_images_self.py
  format_images_in_use.py
```

Every formatter reads exactly ONE JSON file and prints Markdown. Each runs on
its own:

```cmd
python format\format_instances.py json
```

## One command  ->  one JSON file  ->  one formatter

| AWS CLI command (Windows) | JSON file | Formatter |
| --- | --- | --- |
| `aws ec2 describe-instances` | instances.json | format_instances.py |
| `aws ec2 describe-instances` (MetadataOptions) | instances.json | format_metadata.py |
| `aws ec2 describe-instance-status --include-all-instances` | instance_status.json | format_instance_status.py |
| `aws ec2 describe-iam-instance-profile-associations` | iam_instance_profiles.json | format_iam_instance_profiles.py |
| `aws iam get/list-*-role-policies` (via helper) | role_permissions.json | format_role_permissions.py |
| `aws ec2 describe-security-groups` | security_groups.json | format_security_groups.py |
| `aws ec2 describe-security-group-rules` | security_group_rules.json | format_security_group_rules.py |
| `aws ec2 describe-network-interfaces` | network_interfaces.json | format_network_interfaces.py |
| `aws ec2 describe-volumes` | volumes.json | format_volumes.py |
| `aws ec2 describe-subnets` | subnets.json | format_subnets.py |
| `aws ec2 describe-vpcs` | vpcs.json | format_vpcs.py |
| `aws ec2 describe-key-pairs` | key_pairs.json | format_key_pairs.py |
| `aws ec2 describe-tags` | tags.json | format_tags.py |
| `aws ec2 describe-images --owners self` | images_self.json | format_images_self.py |
| `aws ec2 describe-images --image-ids <in use>` | images_in_use.json | format_images_in_use.py |

## Run it

```cmd
REM 1. Fetch all JSON (defaults to us-east-1; pass region and profile if needed)
fetch_all.cmd us-east-1 myprofile

REM 2. Build the Markdown doc from the JSON
python build_docs.py
```

Output: `json\*.json` plus `EC2_DOCUMENTATION.md`.

## Prerequisites

- AWS CLI v2 + Python 3 on PATH
- Read permissions: `ec2:Describe*`, `iam:Get*`, `iam:List*`

## Notes

- **Windows quoting:** cmd.exe uses double quotes `"` around values. The
  `--query`/`--filters` strings here contain no spaces or embedded JSON, so no
  escaping is needed.
- **Relationships** are spelled out in each section's intro ("Join on Instance
  ID with ..."): instance -> AMI, instance -> role -> permissions, instance ->
  security group -> rules, instance -> ENI/subnet/VPC, instance -> volume,
  instance -> key pair.
- `images_in_use.json` resolves AMIs even when owned by Amazon/Marketplace, so
  the instance -> AMI link never has gaps.
