from abc import ABC, abstractmethod
from typing import Self

import httpx

from jira.resources import Issue
from notion.resources import TaskTrackerConfig


class ABCJiraClient(ABC):
    """Abstract client for Jira issue operations."""

    @abstractmethod
    def get_issue(self, code: str) -> Issue:
        """Return a Jira issue by key."""


class JiraClient(ABCJiraClient):
    """HTTP client for Jira issues."""

    def __init__(self, http_client: httpx.Client, browse_base_url: str) -> None:
        """Initialize class instance."""
        self._http_client = http_client
        self._browse_base_url = browse_base_url.rstrip("/")

    @classmethod
    def from_config(cls, config: TaskTrackerConfig) -> Self:
        """Create a Jira client from runtime configuration."""
        if config.jira is None:
            raise ValueError("Jira config is not set")

        http_client = httpx.Client(
            headers={
                "Authorization": f"Bearer {config.jira.api_token}",
                "Accept": "application/json",
            },
            timeout=30,
            base_url=config.jira.base_url,
        )
        return cls(http_client=http_client, browse_base_url=config.jira.base_url)

    def get_issue(self, code: str) -> Issue:
        """Return a Jira issue by key."""
        response = self._http_client.get(f"/rest/api/2/issue/{code}")
        response.raise_for_status()
        return Issue(raw=response.json(), url=f"{self._browse_base_url}/browse/{code}")

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._http_client.close()

    def __enter__(self) -> Self:
        """Enter runtime context."""
        return self

    def __exit__(self, *args: object) -> None:
        """Exit runtime context."""
        self.close()
