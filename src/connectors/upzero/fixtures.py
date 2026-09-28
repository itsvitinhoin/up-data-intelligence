"""Explicit synthetic transport. Never reaches a network, including on unexpected routes."""

import json
from pathlib import Path
from typing import Any

import httpx


def transport(path: str) -> httpx.MockTransport:
    fixtures: dict[str, Any] = json.loads(Path(path).read_text())

    def handle(req: httpx.Request) -> httpx.Response:
        resource = (
            "analytics_facts"
            if req.url.path.endswith("/analytics/facts")
            else req.url.path.rsplit("/", 1)[-1]
        )
        rows = fixtures.get(resource, [])
        limit = int(req.url.params.get("limit", "200"))
        if resource == "customers":
            rows = sorted(rows, key=lambda r: int(r["id"]), reverse=True)
            if "after_id" in req.url.params:
                rows = [r for r in rows if int(r["id"]) < int(req.url.params["after_id"])]
            return httpx.Response(200, json={"data": rows[:limit]})
        if resource == "orders":
            page = int(req.url.params.get("page", "1"))
            return httpx.Response(
                200,
                json={
                    "data": rows[(page - 1) * limit : page * limit],
                    "page": page,
                    "total_pages": max(1, (len(rows) + limit - 1) // limit),
                    "total": len(rows),
                },
            )
        offset = int(req.url.params.get("cursor", "0"))
        return httpx.Response(
            200,
            json={
                "data": rows[offset : offset + limit],
                "next_cursor": str(offset + limit) if offset + limit < len(rows) else None,
                "total": len(rows[offset : offset + limit]),
            },
        )

    return httpx.MockTransport(handle)
