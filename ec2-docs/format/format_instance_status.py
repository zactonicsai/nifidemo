"""Formats: aws ec2 describe-instance-status --include-all-instances
            ->  json/instance_status.json

Health and scheduled-event view. Relates by InstanceId to the Instances table.
"""
from _common import load, table, emit


def main():
    data = load("instance_status")
    rows = []
    for s in data.get("InstanceStatuses", []):
        events = "; ".join(e.get("Code", "") for e in s.get("Events", []) or []) or "-"
        rows.append([
            s.get("InstanceId"),
            s.get("AvailabilityZone"),
            s.get("InstanceState", {}).get("Name"),
            s.get("InstanceStatus", {}).get("Status"),
            s.get("SystemStatus", {}).get("Status"),
            events,
        ])
    md = "## Instance Status (`describe-instance-status`)\n\n"
    md += ("Instance, system and (where present) scheduled-event health. Join on "
           "**Instance ID** with the *Instances* section.\n\n")
    md += table(
        ["Instance ID", "AZ", "State", "Instance Check",
         "System Check", "Scheduled Events"],
        rows)
    emit(md)


if __name__ == "__main__":
    main()
