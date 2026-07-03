from abc import ABC, abstractmethod
from typing import Any, Self

import httpx

from notion.api import (
    NotionError,
    data_sources_api_version,
    notion_headers,
    notion_request,
    paginate_view_query,
    paginated_notion_request,
    supports_data_sources,
    views_api_version,
)
from notion.mapper import page_to_task, task_to_notion_properties
from notion.resources import Task, TaskCreate, TaskTrackerConfig


def is_missing_task_error(error: NotionError) -> bool:
    """Check whether a Notion error means the task cannot be deleted."""
    message = str(error)
    return message.startswith("Notion API error 404:") or (
        message.startswith("Notion API error 400:")
        and "Can't edit block that is archived" in message
    )


class ABCNotionClient(ABC):
    """Abstract client for task tracker operations backed by Notion."""

    @abstractmethod
    def create_task(self, task: TaskCreate) -> Task:
        """Create a task in the tracker."""

    @abstractmethod
    def delete_task(self, task_id: str) -> Task | None:
        """Delete a task by internal ID."""

    @abstractmethod
    def find_task_by_url(self, url: str) -> Task | None:
        """Find a task by URL field."""

    @abstractmethod
    def list_tasks(self) -> list[Task]:
        """List all tasks in the tracker."""

    @abstractmethod
    def list_tasks_by_view(self, view_name: str) -> list[Task]:
        """List tasks through a configured Notion view."""


class NotionClient(ABCNotionClient):
    """HTTP client for a Notion task database."""

    def __init__(self, http_client: httpx.Client, database_id: str, api_version: str) -> None:
        """Initialize class instance."""
        self._http_client = http_client
        self._database_id = database_id
        self._api_version = api_version
        self._data_source_id: str | None = None

    @classmethod
    def from_config(cls, config: TaskTrackerConfig) -> Self:
        """Create a Notion client from runtime configuration."""
        http_client = httpx.Client(
            headers=notion_headers(config.notion.api_token, config.notion.api_version),
            timeout=30,
            base_url=config.notion.base_url,
        )
        return cls(
            http_client=http_client,
            database_id=config.database.id,
            api_version=config.notion.api_version,
        )

    def create_task(self, task: TaskCreate) -> Task:
        """Create a task in the tracker."""
        payload = {
            "parent": self._task_parent(),
            "properties": task_to_notion_properties(task),
        }
        data = notion_request(self._http_client, "POST", "/pages", json=payload)
        return page_to_task(data)

    def delete_task(self, task_id: str) -> Task | None:
        """Delete a task by internal ID."""
        try:
            data = notion_request(
                self._http_client,
                "PATCH",
                f"/pages/{task_id}",
                json=self._delete_task_payload(),
            )
        except NotionError as exc:
            if is_missing_task_error(exc):
                return None
            raise
        return page_to_task(data)

    def _delete_task_payload(self) -> dict[str, bool]:
        """Build the task deletion payload for the configured API version."""
        if supports_data_sources(self._api_version):
            return {"in_trash": True}
        return {"archived": True}

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
            self._query_path(),
            json=payload,
        )
        results = data.get("results", [])
        if not results:
            return None
        return page_to_task(results[0])

    def list_tasks(self) -> list[Task]:
        """List all tasks in the tracker."""
        return [
            page_to_task(page)
            for page in paginated_notion_request(
                self._http_client,
                "POST",
                self._query_path(),
            )
        ]

    def list_tasks_by_view(self, view_name: str) -> list[Task]:
        """List tasks through a configured Notion view."""
        view_id = self._find_view_id_by_name(view_name)
        query = notion_request(
            self._http_client,
            "POST",
            f"/views/{view_id}/queries",
            json={"page_size": 100},
            notion_version=views_api_version(self._api_version),
        )
        query_id = str(query["id"])
        try:
            return [
                page_to_task(page)
                for page in self._hydrate_pages(
                    paginate_view_query(
                        self._http_client,
                        view_id,
                        query_id,
                        query,
                        views_api_version(self._api_version),
                    )
                )
            ]
        finally:
            notion_request(
                self._http_client,
                "DELETE",
                f"/views/{view_id}/queries/{query_id}",
                notion_version=views_api_version(self._api_version),
            )

    def _task_parent(self) -> dict[str, str]:
        """Build a Notion parent object for new tasks."""
        if supports_data_sources(self._api_version):
            return {"data_source_id": self._get_data_source_id()}
        return {"database_id": self._database_id}

    def _query_path(self) -> str:
        """Build the task query endpoint for the configured API version."""
        if supports_data_sources(self._api_version):
            return f"/data_sources/{self._get_data_source_id()}/query"
        return f"/databases/{self._database_id}/query"

    def _get_data_source_id(self) -> str:
        """Return the first data source ID for the configured database."""
        if self._data_source_id is not None:
            return self._data_source_id

        database = notion_request(
            self._http_client,
            "GET",
            f"/databases/{self._database_id}",
            notion_version=data_sources_api_version(self._api_version),
        )
        data_sources = database.get("data_sources", [])
        if not data_sources:
            raise NotionError(f'Database "{self._database_id}" has no data sources')

        self._data_source_id = str(data_sources[0]["id"])
        return self._data_source_id

    def _hydrate_pages(self, pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Retrieve full page objects for page references."""
        hydrated_pages: list[dict[str, Any]] = []
        for page in pages:
            if page.get("properties"):
                hydrated_pages.append(page)
                continue
            hydrated_pages.append(
                notion_request(
                    self._http_client,
                    "GET",
                    f"/pages/{page['id']}",
                    notion_version=self._api_version,
                )
            )
        return hydrated_pages

    def _find_view_id_by_name(self, view_name: str) -> str:
        """Find a Notion view ID by exact display name."""
        view_refs = paginated_notion_request(
            self._http_client,
            "GET",
            "/views",
            params={"database_id": self._database_id},
            notion_version=views_api_version(self._api_version),
        )
        for view_ref in view_refs:
            view = notion_request(
                self._http_client,
                "GET",
                f"/views/{view_ref['id']}",
                notion_version=views_api_version(self._api_version),
            )
            if view.get("name") == view_name:
                return str(view["id"])

        raise NotionError(f'View "{view_name}" was not found')

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._http_client.close()

    def __enter__(self) -> Self:
        """Enter runtime context."""
        return self

    def __exit__(self, *args: object) -> None:
        """Exit runtime context."""
        self.close()
