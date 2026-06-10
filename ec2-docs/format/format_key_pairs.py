"""Formats: aws ec2 describe-key-pairs  ->  json/key_pairs.json

SSH key-pair inventory. Join on Key Name with the *Instances* section
(the KeyName column).
"""
from _common import load, table, emit


def main():
    data = load("key_pairs")
    rows = []
    for k in data.get("KeyPairs", []):
        rows.append([
            k.get("KeyName"),
            k.get("KeyPairId"),
            k.get("KeyType"),
            k.get("KeyFingerprint", "")[:24],
            k.get("CreateTime", "")[:19] if k.get("CreateTime") else "",
        ])
    md = "## Key Pairs (`describe-key-pairs`)\n\n"
    md += ("Registered SSH key pairs. Join on **Key Name** with the *Instances* "
           "section to see which instance uses each key.\n\n")
    md += table(
        ["Key Name", "Key ID", "Type", "Fingerprint", "Created"],
        rows)
    emit(md)


if __name__ == "__main__":
    main()
