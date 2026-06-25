from notion.client import ABCNotionClient
from notion.resources import Task, TaskCreate, TaskLevel, TaskStatus
from task_tracker.resources import (
    PullRequestRef,
    TaskAddResult,
    TaskDeleteResult,
    TaskOverrides,
    parse_github_pull_request_url,
)


class TaskTrackerClient:
    """Business client for task tracker operations."""

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
                    default_task_level=TaskLevel.MEDIUM,
                    default_task_status=TaskStatus.PLANNING,
                    overrides=overrides,
                )
            ),
            created=True,
        )

    def delete_task(self, task_id: str) -> TaskDeleteResult:
        """Delete a task by internal ID."""
        return self.delete_tasks([task_id])

    def delete_tasks(self, task_ids: list[str]) -> TaskDeleteResult:
        """Delete tasks by internal IDs."""
        tasks: list[Task] = []
        for task_id in task_ids:
            tasks.append(self._delete_task(task_id))
        return TaskDeleteResult(tasks=tasks)

    def _delete_task(self, task_id: str) -> Task:
        """Delete one task by internal ID."""
        task = self._notion_client.delete_task(task_id)
        if task is None:
            raise ValueError(f'Task "{task_id}" was not found.')
        return task

    def list_tasks(self, view_name: str | None = None) -> list[Task]:
        """List tasks with an optional Notion view name."""
        if view_name is None:
            return self._notion_client.list_tasks()
        return self._notion_client.list_tasks_by_view(view_name)


def build_task(
    name: str,
    *,
    default_url: str | None = None,
    default_task_level: TaskLevel | None = None,
    default_task_status: TaskStatus = TaskStatus.TODO,
    overrides: TaskOverrides | None = None,
) -> TaskCreate:
    """Build a task payload from defaults and overrides."""
    if overrides is None:
        overrides = TaskOverrides()

    return TaskCreate(
        name=overrides.name or name,
        level=parse_level(overrides.level) if overrides.level else default_task_level,
        status=parse_status(overrides.status) if overrides.status else default_task_status,
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
    status = TaskStatus.from_value(value)
    if not status:
        allowed = ", ".join(status.value for status in TaskStatus)
        raise ValueError(f"Invalid status {value!r}. Allowed values: {allowed}.")

    return status
