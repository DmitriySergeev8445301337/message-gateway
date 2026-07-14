from __future__ import annotations

import heapq
import itertools
import os
from typing import *

from flask import Flask, jsonify, request


app = Flask(__name__)

adapt = {}



def value_equal(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return float(a) == float(b)
    if a is None or b is None:
        return a is None and b is None
    return type(a) == type(b) and a == b


def normalize_value(v):
    if v is None:
        return (0, None)
    if isinstance(v, bool):
        return (1, v)
    if isinstance(v, (int, float)):
        return (2, float(v))
    return (3, v)


def state_key(service, message):
    return (service, frozenset((k, normalize_value(v)) for k, v in message.items()))


def apply_operations(message, operations):
    msg = dict(message)
    lost = []
    for op in operations:
        kind = op["op"]
        if kind == "rename":
            f1 = op["from"]
            f2 = op["to"]
            if f1 not in msg or f2 in msg:
                return None
            msg[f2] = msg.pop(f1)
        elif kind == "default":
            f1 = op["field"]
            v = op["value"]
            if f1 not in msg:
                msg[f1] = v
        elif kind == "map":
            f1 = op["field"]
            if f1 not in msg:
                return None
            cur = msg[f1]
            matched = False
            for entry in op["values"]:
                if value_equal(cur, entry["from"]):
                    msg[f1] = entry["to"]
                    matched = True
        elif kind == "drop":
            f1 = op["field"]
            if f1 in msg:
                lost.append(f1)
        else:
            return None

    return msg, lost


def find_route(src, dst, message):
    counter = itertools.count()
    start = (0, 0, 0,(src,), next(counter), [], message)
    heap = [start]
    visited = set()
    while heap:
        cost, hops, path, _, lost_fields, msg = heapq.heappop(heap)
        service = path[-1]
        skey = state_key(service, msg)
        if skey in visited:
            continue
        if service == dst:
            return {"status": "routed","path": list(path), "message": msg, "lost_fields": lost_fields, "cost": cost}
        for nxt, edge_cost, operations in adapt.get(service, []):
            applied = apply_operations(msg, operations)
            if applied is None:
                continue
            new_msg, new_lost = applied
            nkey = state_key(nxt, new_msg)
            if nkey in visited:
                continue

            new_path = path + (nxt,)
            new_lost_fields = lost_fields + new_lost
            heapq.heappush(heap, (len(new_lost_fields), cost + edge_cost, hops + 1, new_path, next(counter),new_lost_fields, new_msg,))

    return {"status": "incompatible", "reason_code": "NO_APPLICABLE_PATH"}


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.post("/configure")
def configure():
    global adapt
    payload = request.get_json(force=True)
    adapters = payload["adapters"]

    new_adapters: Dict[str, List[Tuple[str, int, List[dict]]]] = {}
    for adapter in adapters:
        src = adapter["from"]
        dst = adapter["to"]
        cost = adapter["cost"]
        operations = adapter["operations"]
        new_adapters.setdefault(src, []).append((dst, cost, operations))

    adapt = new_adapters
    return jsonify({"status": "ok"})


@app.post("/route")
def route():
    payload = request.get_json(force=True)
    src = payload["from"]
    dst = payload["to"]
    message = payload["message"]

    result = find_route(src, dst, message)
    return jsonify(result)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, threaded=False)
