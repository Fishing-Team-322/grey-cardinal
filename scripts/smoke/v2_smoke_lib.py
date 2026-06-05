from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import httpx


def unique_email(prefix: str) -> str:
    return f"{prefix}-{int(time.time() * 1000)}@example.com"


@dataclass
class V2SmokeClient:
    base_url: str = os.getenv("SMOKE_BASE_URL", "http://localhost:8000")
    internal_token: str = os.getenv("INTERNAL_API_TOKEN", "dev-internal-token")
    session_cookie: str | None = None

    def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        headers = dict(kwargs.pop("headers", {}) or {})
        if self.session_cookie:
            headers["Cookie"] = f"gc_session={self.session_cookie}"
        with httpx.Client(base_url=self.base_url, timeout=30.0, follow_redirects=True) as client:
            response = client.request(method, path, headers=headers, **kwargs)
        if response.status_code >= 400:
            raise RuntimeError(f"{method} {path} -> {response.status_code}: {response.text}")
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    def register(self, prefix: str, first_name: str, last_name: str) -> dict[str, Any]:
        email = unique_email(prefix)
        with httpx.Client(base_url=self.base_url, timeout=30.0) as client:
            response = client.post(
                "/api/auth/register",
                json={
                    "email": email,
                    "login": email.split("@", 1)[0],
                    "first_name": first_name,
                    "last_name": last_name,
                    "password": "SmokePass123",
                },
            )
        if response.status_code >= 400:
            raise RuntimeError(f"register -> {response.status_code}: {response.text}")
        self.session_cookie = response.cookies.get("gc_session")
        return response.json()

    def internal(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request(
            "POST",
            path,
            json=payload,
            headers={"X-Internal-Token": self.internal_token},
        )


def create_director_company(client: V2SmokeClient) -> tuple[dict[str, Any], dict[str, Any]]:
    director = client.register("director", "Smoke", "Director")
    company = client.request(
        "POST",
        "/api/companies",
        json={"name": "Smoke Company", "timezone": "Europe/Moscow"},
    )
    return director, company


def create_team(client: V2SmokeClient, company_id: str, name: str) -> dict[str, Any]:
    return client.request(
        "POST",
        f"/api/companies/{company_id}/teams",
        json={"name": name},
    )


def create_team_invite(
    client: V2SmokeClient, company_id: str, team_id: str, role: str
) -> dict[str, Any]:
    return client.request(
        "POST",
        f"/api/companies/{company_id}/invites",
        json={"scope": "team", "team_id": team_id, "role": role, "expires_hours": 2},
    )
