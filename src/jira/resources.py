from typing import Any

from pydantic import BaseModel, Field


class JiraConfig(BaseModel):
    """Runtime settings for connecting to the Jira API."""

    base_url: str
    api_token: str


class Issue(BaseModel):
    """Jira issue."""

    raw: dict[str, Any] = Field(default_factory=dict)
    url: str | None = None

    @property
    def code(self) -> str:
        """Return Jira issue key."""
        key = self.raw.get("key")
        if isinstance(key, str):
            return key

        if self.url:
            return self.url.split("/")[-1]

        return ""

    @property
    def assignee(self) -> str | None:
        """Return Jira issue assignee username."""
        fields = self._fields
        assignee = fields.get("assignee")
        if not isinstance(assignee, dict):
            return None

        name = assignee.get("name")
        return name if isinstance(name, str) else None

    @property
    def labels(self) -> list[str]:
        """Return Jira issue labels."""
        labels = self._fields.get("labels")
        if not isinstance(labels, list):
            return []
        return [label for label in labels if isinstance(label, str)]

    @property
    def description(self) -> str | None:
        """Return Jira issue description."""
        description = self._fields.get("description")
        return description if isinstance(description, str) else None

    @property
    def status(self) -> str | None:
        """Return Jira issue status name."""
        status = self._fields.get("status")
        if not isinstance(status, dict):
            return None

        name = status.get("name")
        return name if isinstance(name, str) else None

    @property
    def priority(self) -> str | None:
        """Return Jira issue priority name."""
        priority = self._fields.get("priority")
        if not isinstance(priority, dict):
            return None

        name = priority.get("name")
        return name if isinstance(name, str) else None

    @property
    def summary(self) -> str | None:
        """Return Jira issue summary."""
        summary = self._fields.get("summary")
        return summary if isinstance(summary, str) else None

    @property
    def title(self) -> str | None:
        """Return Jira issue title."""
        return self.summary

    @property
    def _fields(self) -> dict[str, Any]:
        """Return raw Jira issue fields."""
        fields = self.raw.get("fields")
        return fields if isinstance(fields, dict) else {}
