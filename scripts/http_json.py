import json
import sys

import requests


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: python scripts/http_json.py <method> <url> [json_payload]", file=sys.stderr)
        return 2

    method = sys.argv[1].upper()
    url = sys.argv[2]
    payload = json.loads(sys.argv[3]) if len(sys.argv) > 3 else None

    response = requests.request(method=method, url=url, json=payload, timeout=60)
    print(json.dumps({"status": response.status_code, "body": response.json()}, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
