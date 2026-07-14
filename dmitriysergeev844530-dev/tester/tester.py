from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Tuple


def typed_json_equal(a: Any, b: Any) -> bool:
    """JSON equality used by the checker: dict order is ignored, list order is not."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return float(a) == float(b)
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(typed_json_equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(typed_json_equal(x, y) for x, y in zip(a, b))
    return a == b


def post_json(base_url: str, path: str, payload: dict, timeout: float) -> Tuple[Any, float]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    start = time.perf_counter()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read()
    elapsed = time.perf_counter() - start
    return json.loads(body.decode("utf-8")), elapsed


def get_json(base_url: str, path: str, timeout: float) -> Tuple[Any, float]:
    request = urllib.request.Request(base_url.rstrip("/") + path, method="GET")
    start = time.perf_counter()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read()
    elapsed = time.perf_counter() - start
    return json.loads(body.decode("utf-8")), elapsed


def main() -> int:
    parser = argparse.ArgumentParser(description="Run public tests for the message gateway")
    parser.add_argument("--url", default="http://localhost:8080", help="solution base URL")
    parser.add_argument(
        "--tests",
        default=str(Path(__file__).with_name("public_tests.json")),
        help="path to public_tests.json",
    )
    parser.add_argument("--timeout", type=float, default=3.0, help="HTTP timeout per request")
    parser.add_argument("--case", default="", help="run only cases whose name contains this text")
    args = parser.parse_args()

    with open(args.tests, "r", encoding="utf-8") as file:
        suite = json.load(file)

    cases = suite["cases"]
    if args.case:
        cases = [case for case in cases if args.case in case["name"]]
    if not cases:
        print("No test cases selected", file=sys.stderr)
        return 2

    failures = []
    checks = 0
    max_request = 0.0

    try:
        actual, elapsed = get_json(args.url, "/health", args.timeout)
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        print(f"/health failed: {exc!r}", file=sys.stderr)
        return 2

    max_request = max(max_request, elapsed)
    if not typed_json_equal(actual, {"status": "ok"}):
        print(f"/health returned {actual!r}, expected {{'status': 'ok'}}", file=sys.stderr)
        return 1
    print(f"/health: OK ({elapsed * 1000:.1f} ms)", flush=True)

    for case in cases:
        print(f"== {case['name']} ==", flush=True)
        try:
            actual, elapsed = post_json(
                args.url, "/configure", {"adapters": case["adapters"]}, args.timeout
            )
        except (OSError, urllib.error.URLError, TimeoutError) as exc:
            print(f"  /configure failed: {exc!r}", flush=True)
            return 2

        max_request = max(max_request, elapsed)
        if not typed_json_equal(actual, {"status": "ok"}):
            failures.append(f"{case['name']}: /configure returned {actual!r}")
            print("  configure: FAIL", flush=True)
            continue
        print(f"  configure: OK ({elapsed * 1000:.1f} ms)", flush=True)

        for route in case["routes"]:
            request = route["request"]
            payload = {
                "from": request["from"],
                "to": request["to"],
                "message": request["message"],
            }
            label = f"{case['name']}/{route['name']}"
            try:
                actual, elapsed = post_json(args.url, "/route", payload, args.timeout)
            except (OSError, urllib.error.URLError, TimeoutError) as exc:
                failures.append(f"{label}: request failed: {exc!r}")
                print(f"  {route['name']}: FAIL ({exc!r})", flush=True)
                continue

            checks += 1
            max_request = max(max_request, elapsed)
            expected = route["expected"]
            if typed_json_equal(actual, expected):
                print(f"  {route['name']}: OK ({elapsed * 1000:.1f} ms)", flush=True)
            else:
                failures.append(
                    f"{label}: wrong answer\n"
                    f"  request:  {json.dumps(payload, ensure_ascii=False, sort_keys=True)}\n"
                    f"  expected: {json.dumps(expected, ensure_ascii=False, sort_keys=True)}\n"
                    f"  actual:   {json.dumps(actual, ensure_ascii=False, sort_keys=True)}"
                )
                print(f"  {route['name']}: FAIL", flush=True)

    print("\n================ SUMMARY ================", flush=True)
    print(f"checks:      {checks}", flush=True)
    print(f"max request: {max_request * 1000:.1f} ms", flush=True)
    if failures:
        print(f"result:      FAIL ({len(failures)} problem(s))", flush=True)
        print("\nPROBLEMS:", flush=True)
        for failure in failures[:10]:
            print(f"- {failure}", flush=True)
        if len(failures) > 10:
            print(f"... and {len(failures) - 10} more", flush=True)
        return 1

    print("result:      OK", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
