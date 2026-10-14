"""JSON-only custom regex batch; never imports IDA or calls native helpers."""

import json
import re
import sys


def match_batches(payload):
    scans = []
    for pattern, batch in zip(payload["patterns"], payload["batches"], strict=True):
        regex = re.compile(pattern, re.IGNORECASE)
        indices, scanned, text_truncated = [], 0, False
        for index, (text, truncated) in enumerate(batch["subjects"]):
            if len(indices) >= payload["max_matches"]:
                break
            scanned += 1
            text_truncated |= truncated
            if regex.search(text):
                indices.append(index)
        scans.append({"indices": indices, "coverage": {
            "total": batch["total"], "scanned": scanned,
            "scan_truncated": scanned < batch["total"],
            "matches": len(indices), "text_truncated": text_truncated,
        }})
    return scans


if __name__ == "__main__":
    print(json.dumps(match_batches(json.load(sys.stdin))))
