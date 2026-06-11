from datetime import date, timedelta
from urllib.parse import urlparse

from pydantic import BaseModel, field_validator

from notion.resources import Task


class PullRequestRef(BaseModel):
    """Pull request reference parsed from a Git hosting URL."""

    owner: str
    repo: str
    number: int
    url: str

    @property
    def task_name(self) -> str:
        """Build the default task name for this pull request."""
        return f"PR #{self.number} {self.owner}/{self.repo}"


class TaskOverrides(BaseModel):
    """Optional task fields supplied from CLI flags."""

    name: str | None = None
    level: str | None = None
    status: str | None = None
    until: date | None = None
    url: str | None = None

    @field_validator("name", "level", "status", "url")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        """Normalize optional CLI text fields."""
        if value is None:
            return None
        value = value.strip()
        return value or None


class TaskAddResult(BaseModel):
    """Result of adding or finding a task."""

    task: Task
    created: bool


class TaskDeleteResult(BaseModel):
    """Result of deleting tasks."""

    tasks: list[Task]

    @property
    def task(self) -> Task:
        """Return the first deleted task."""
        return self.tasks[0]


def parse_date_offset(value: str) -> date:
    """Parse ISO date or relative day offset."""
    try:
        offset = int(value)
    except ValueError:
        return date.fromisoformat(value)
    return date.today() + timedelta(days=offset)


def parse_github_pull_request_url(value: str) -> PullRequestRef | None:
    """Parse a GitHub or GitLab pull request URL."""
    parsed = urlparse(value)
    host = parsed.hostname or ""
    if parsed.scheme not in {"http", "https"} or not is_git_host(host):
        return None

    parts = [part for part in parsed.path.split("/") if part]
    pull_marker = pull_request_marker_index(parts)
    if pull_marker is None or pull_marker + 1 >= len(parts):
        return None
    repo_marker = repository_marker_index(parts, pull_marker)
    if repo_marker < 1:
        return None

    try:
        number = int(parts[pull_marker + 1])
    except ValueError:
        return None

    return PullRequestRef(
        owner="/".join(parts[:repo_marker]),
        repo=parts[repo_marker],
        number=number,
        url=value,
    )


def is_git_host(host: str) -> bool:
    """Check if a hostname looks like GitHub or GitLab."""
    normalized = host.lower()
    return "github" in normalized or "gitlab" in normalized


def pull_request_marker_index(parts: list[str]) -> int | None:
    """Find the path segment that identifies a pull request."""
    if "pull" in parts:
        return parts.index("pull")
    if "merge_requests" in parts:
        return parts.index("merge_requests")
    return None


def repository_marker_index(parts: list[str], pull_marker: int) -> int:
    """Find the path segment that identifies the repository."""
    if pull_marker > 0 and parts[pull_marker - 1] == "-":
        return pull_marker - 2
    return pull_marker - 1
