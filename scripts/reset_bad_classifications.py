"""One-off script: Reset items that were classified with the buggy parser.

The bug: HF API changed response format from {labels: [], scores: []} to
[{label: str, score: float}, ...]. Our parser returned unknown/0.0 for everything.

This resets label to "" for those items so query_unprocessed() picks them up again.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import boto3
from boto3.dynamodb.conditions import Attr

from src.config import AWS_REGION, DYNAMODB_TABLE


def reset_bad_classifications() -> int:
    dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
    table = dynamodb.Table(DYNAMODB_TABLE)

    # Find items with confidence=0.0 and label=unknown (the buggy output)
    response = table.scan(
        FilterExpression=Attr("label").eq("unknown") & Attr("confidence").eq("0.0"),
    )
    items = response.get("Items", [])

    # Handle pagination
    while "LastEvaluatedKey" in response:
        response = table.scan(
            FilterExpression=Attr("label").eq("unknown") & Attr("confidence").eq("0.0"),
            ExclusiveStartKey=response["LastEvaluatedKey"],
        )
        items.extend(response.get("Items", []))

    print(f"Found {len(items)} items to reset")

    reset_count = 0
    for item in items:
        table.update_item(
            Key={"item_id": item["item_id"]},
            UpdateExpression="SET #lbl = :empty, confidence = :empty",
            ExpressionAttributeNames={"#lbl": "label"},
            ExpressionAttributeValues={":empty": ""},
        )
        reset_count += 1
        if reset_count % 50 == 0:
            print(f"  Reset {reset_count}/{len(items)}...")

    print(f"Done. Reset {reset_count} items. They will be re-processed on next run.")
    return reset_count


if __name__ == "__main__":
    reset_bad_classifications()
