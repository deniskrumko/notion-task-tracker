from abc import ABC, abstractmethod
from datetime import date
from typing import Any, Self

import httpx

from notion.resources import Task, TaskCreate, TaskLevel, TaskStatus, TaskTrackerConfig


class NotionError(RuntimeError):
    """Notion client operation failed."""


class ABCNotionClient(ABC):
    """Abstract client for task tracker operations backed by Notion."""

    @abstractmethod
    def create_task(self, task: TaskCreate) -> Task:
        """Create a task in the tracker."""

    @abstractmethod
    def find_task_by_url(self, url: str) -> Task | None:
        """Find a task by URL field."""


class NotionClient(ABCNotionClient):
    """HTTP client for a Notion task database."""

    def __init__(self, http_client: httpx.Client, database_id: str) -> None:
        """Initialize class instance."""
        self._http_client = http_client
        self._database_id = database_id

    @classmethod
    def from_config(cls, config: TaskTrackerConfig) -> Self:
        """Create a Notion client from runtime configuration."""
        http_client = httpx.Client(
            headers=notion_headers(config.notion.api_token, config.notion.api_version),
            timeout=30,
            base_url=config.notion.base_url,
        )
        return cls(http_client=http_client, database_id=config.database.id)

    def create_task(self, task: TaskCreate) -> Task:
        """Create a task in the tracker."""
        payload = {
            "parent": {"database_id": self._database_id},
            "properties": task_to_notion_properties(task),
        }
        data = notion_request(self._http_client, "POST", "/pages", json=payload)
        return page_to_task(data)

    def find_task_by_url(self, url: str) -> Task | None:
        """Find a task by URL field."""
        payload = {
            "filter": {
                "property": "URL",
                "url": {
                    "equals": url,
                },
            },
            "page_size": 1,
        }
        data = notion_request(
            self._http_client,
            "POST",
            f"/databases/{self._database_id}/query",
            json=payload,
        )
        results = data.get("results", [])
        if not results:
            return None
        return page_to_task(results[0])

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._http_client.close()

    def __enter__(self) -> Self:
        """Enter runtime context."""
        return self

    def __exit__(self, *args: object) -> None:
        """Exit runtime context."""
        self.close()


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
) -> dict[str, Any]:
    """Execute a Notion API request and return JSON."""
    response = client.request(method, path, json=json)

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


def extract_plain_text(items: list[dict[str, Any]]) -> str:
    """Extract plain text from Notion rich text fragments."""
    return "".join(item.get("plain_text", "") for item in items).strip()


def database_title(database: dict[str, Any]) -> str:
    """Extract a database title from Notion search data."""
    return extract_plain_text(database.get("title", []))


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
            raise NotionError(f'Database "{database_name}" was not found.')

        cursor = data.get("next_cursor")


def task_to_notion_properties(task: TaskCreate) -> dict[str, Any]:
    """Convert a task payload into Notion page properties."""
    properties: dict[str, Any] = {
        "Task name": {
            "title": [
                {
                    "text": {
                        "content": task.name,
                    },
                },
            ],
        },
        "Status": {"status": {"name": task.status.value}},
    }
    if task.level is not None:
        properties["Level"] = {"select": {"name": task.level.value}}
    if task.until is not None:
        properties["Until"] = {"date": {"start": task.until.isoformat()}}
    if task.url is not None:
        properties["URL"] = {"url": task.url}
    return properties


def page_to_task(page: dict[str, Any]) -> Task:
    """Convert a Notion page object into a task."""
    properties = page.get("properties", {})
    return Task(
        id=str(page["id"]),
        name=property_title(properties.get("Task name", {})) or "Untitled",
        level=property_task_level(properties.get("Level", {})),
        status=TaskStatus(property_status_name(properties.get("Status", {})) or TaskStatus.TODO),
        until=property_date(properties.get("Until", {})),
        url=property_url(properties.get("URL", {})),
    )


def property_title(prop: dict[str, Any]) -> str:
    """Extract a title property value."""
    return extract_plain_text(prop.get("title", []))


def property_select_name(prop: dict[str, Any]) -> str:
    """Extract a select property name."""
    return (prop.get("select") or {}).get("name", "")


def property_task_level(prop: dict[str, Any]) -> TaskLevel | None:
    """Extract a task level property value."""
    value = property_select_name(prop)
    if not value:
        return None
    return TaskLevel(value)


def property_status_name(prop: dict[str, Any]) -> str:
    """Extract a status property name."""
    return (prop.get("status") or {}).get("name", "")


def property_date(prop: dict[str, Any]) -> date | None:
    """Extract a date property start value."""
    date_data = prop.get("date") or {}
    value = date_data.get("start")
    if value is None:
        return None
    return date.fromisoformat(value)


def property_url(prop: dict[str, Any]) -> str | None:
    """Extract a URL property value."""
    return prop.get("url") or None
