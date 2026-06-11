from notion.client import ABCNotionClient
from notion.resources import TaskCreate, TaskLevel, TaskStatus
from task_tracker.resources import (
    PullRequestRef,
    TaskAddResult,
    TaskOverrides,
    parse_github_pull_request_url,
)


class TaskTrackerClient:
    """Business client for adding tasks to the tracker."""

    def __init__(self, notion_client: ABCNotionClient) -> None:
        """Initialize class instance."""
        self._notion_client = notion_client

    def add_auto(self, value: str, overrides: TaskOverrides) -> TaskAddResult:
        """Add a task using automatic input detection."""
        pull_request = parse_github_pull_request_url(value)
        if pull_request is not None:
            return self.add_pull_request(pull_request, overrides)

        return TaskAddResult(
            task=self._notion_client.create_task(
                build_task(
                    name=value,
                    default_url=None,
                    overrides=overrides,
                )
            ),
            created=True,
        )

    def add_pull_request(
        self,
        pull_request: PullRequestRef,
        overrides: TaskOverrides,
    ) -> TaskAddResult:
        """Add a pull request task if it does not already exist."""
        existing = self._notion_client.find_task_by_url(pull_request.url)
        if existing is not None:
            return TaskAddResult(task=existing, created=False)

        return TaskAddResult(
            task=self._notion_client.create_task(
                build_task(
                    name=pull_request.task_name,
                    default_url=pull_request.url,
                    overrides=overrides,
                )
            ),
            created=True,
        )


def build_task(name: str, default_url: str | None, overrides: TaskOverrides) -> TaskCreate:
    """Build a task payload from defaults and overrides."""
    return TaskCreate(
        name=overrides.name or name,
        level=parse_level(overrides.level) if overrides.level else None,
        status=parse_status(overrides.status) if overrides.status else TaskStatus.TODO,
        until=overrides.until,
        url=overrides.url or default_url,
    )


def parse_level(value: str) -> TaskLevel:
    """Parse task level including shorthand values."""
    normalized = value.strip().lower()
    mapping = {
        "l": TaskLevel.LOW,
        "low": TaskLevel.LOW,
        "m": TaskLevel.MEDIUM,
        "medium": TaskLevel.MEDIUM,
        "h": TaskLevel.HIGH,
        "high": TaskLevel.HIGH,
    }
    if normalized not in mapping:
        allowed = ", ".join(level.value for level in TaskLevel)
        raise ValueError(f"Invalid level {value!r}. Allowed values: {allowed}.")
    return mapping[normalized]


def parse_status(value: str) -> TaskStatus:
    """Parse task status value."""
    normalized = value.strip().lower()
    for status in TaskStatus:
        if status.value.lower() == normalized:
            return status
    allowed = ", ".join(status.value for status in TaskStatus)
    raise ValueError(f"Invalid status {value!r}. Allowed values: {allowed}.")
