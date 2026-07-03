from datetime import date
from typing import Any

import httpx

from notion.mapper import database_title

VIEWS_API_VERSION = "2025-09-03"


class NotionError(RuntimeError):
    """Notion client operation failed."""


def notion_headers(token: str, api_version: str) -> dict[str, str]:
    """Build HTTP headers for Notion API requests."""
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": api_version,
        "Content-Type": "application/json",
    }


def notion_request(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    json: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    notion_version: str | None = None,
) -> dict[str, Any]:
    """Execute a Notion API request and return JSON."""
    headers = {"Notion-Version": notion_version} if notion_version else None
    response = client.request(method, path, json=json, params=params, headers=headers)

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        message = response.text
        try:
            payload = response.json()
            message = payload.get("message", message)
        except ValueError:
            pass
        raise NotionError(f"Notion API error {response.status_code}: {message}") from exc

    return response.json()


def paginated_notion_request(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    json: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    notion_version: str | None = None,
) -> list[dict[str, Any]]:
    """Collect all results from a paginated Notion list endpoint."""
    cursor: str | None = None
    results: list[dict[str, Any]] = []

    while True:
        page_json = dict(json or {})
        page_params = dict(params or {})
        if cursor is not None:
            if method == "GET":
                page_params["start_cursor"] = cursor
            else:
                page_json["start_cursor"] = cursor
        if method != "GET":
            page_json.setdefault("page_size", 100)
        else:
            page_params.setdefault("page_size", 100)

        data = notion_request(
            client,
            method,
            path,
            json=page_json if method != "GET" else json,
            params=page_params,
            notion_version=notion_version,
        )
        results.extend(data.get("results", []))

        if not data.get("has_more"):
            return results
        cursor = data.get("next_cursor")


def paginate_view_query(
    client: httpx.Client,
    view_id: str,
    query_id: str,
    first_page: dict[str, Any],
    notion_version: str,
) -> list[dict[str, Any]]:
    """Collect all page results from a Notion view query."""
    results = list(first_page.get("results", []))
    cursor = first_page.get("next_cursor")

    while first_page.get("has_more") and cursor:
        data = notion_request(
            client,
            "GET",
            f"/views/{view_id}/queries/{query_id}",
            params={"start_cursor": cursor, "page_size": 100},
            notion_version=notion_version,
        )
        results.extend(data.get("results", []))
        cursor = data.get("next_cursor")
        first_page = data

    return results


def views_api_version(api_version: str) -> str:
    """Return a Notion API version that supports database views."""
    if supports_data_sources(api_version):
        return api_version
    return VIEWS_API_VERSION


def data_sources_api_version(api_version: str) -> str:
    """Return a Notion API version that supports data sources."""
    if supports_data_sources(api_version):
        return api_version
    return VIEWS_API_VERSION


def supports_data_sources(api_version: str) -> bool:
    """Check whether the configured API version uses data sources."""
    try:
        configured = date.fromisoformat(api_version)
    except ValueError as exc:
        raise NotionError(f"Invalid Notion API version: {api_version}") from exc

    minimum = date.fromisoformat(VIEWS_API_VERSION)
    return configured >= minimum


def find_database_id(client: httpx.Client, database_name: str) -> str:
    """Find a Notion database ID by exact title."""
    cursor: str | None = None

    while True:
        payload: dict[str, Any] = {
            "filter": {"property": "object", "value": "database"},
            "page_size": 100,
        }
        if cursor:
            payload["start_cursor"] = cursor

        data = notion_request(client, "POST", "/search", json=payload)

        for database in data.get("results", []):
            if database_title(database) == database_name:
                return str(database["id"])

        if not data.get("has_more"):
            raise NotionError(f'Database "{database_name}" was not found')

        cursor = data.get("next_cursor")
