"""Formats the MetadataOptions block from: aws ec2 describe-instances
            ->  json/instances.json

IMDS settings (IMDSv2 enforcement, hop limit, metadata-tags). Kept separate
because metadata is its own configuration concern. Join on InstanceId.
"""
from _common import load, table, name_tag, emit


def main():
    data = load("instances")
    rows = []
    for r in data.get("Reservations", []):
        for i in r.get("Instances", []):
            m = i.get("MetadataOptions", {})
            rows.append([
                i.get("InstanceId"),
                name_tag(i),
                m.get("HttpTokens"),          # 'required' => IMDSv2 enforced
                m.get("HttpEndpoint"),
                m.get("HttpPutResponseHopLimit"),
                m.get("InstanceMetadataTags"),
                m.get("HttpProtocolIpv6"),
            ])
    md = "## Metadata Settings / IMDS (`describe-instances` \u2192 MetadataOptions)\n\n"
    md += ("`HttpTokens=required` means **IMDSv2 is enforced** (recommended). A "
           "hop limit greater than 1 can let containers reach instance "
           "credentials. Join on **Instance ID** with the *Instances* section.\n\n")
    md += table(
        ["Instance ID", "Name", "HttpTokens", "Endpoint",
         "Hop Limit", "Metadata Tags", "IPv6"],
        rows)
    emit(md)


if __name__ == "__main__":
    main()
