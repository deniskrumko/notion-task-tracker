from jira.client import ABCJiraClient
from jira.resources import Issue
from notion.client import ABCNotionClient
from notion.resources import Task, TaskCreate, TaskLevel, TaskStatus
from task_tracker.resources import (
    PullRequestRef,
    TaskAddResult,
    TaskDeleteResult,
    TaskOverrides,
    parse_github_pull_request_url,
    parse_jira_issue_code,
)


class TaskTrackerClient:
    """Business client for task tracker operations."""

    def __init__(
        self,
        notion_client: ABCNotionClient,
        jira_client: ABCJiraClient | None = None,
    ) -> None:
        """Initialize class instance."""
        self._notion_client = notion_client
        self._jira_client = jira_client

    def add_auto(
        self, value: str, overrides: TaskOverrides, *, force: bool = False
    ) -> TaskAddResult:
        """Add a task using automatic input detection."""
        pull_request = parse_github_pull_request_url(value)
        if pull_request is not None:
            return self.add_pull_request(pull_request, overrides, force=force)

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
        *,
        force: bool = False,
    ) -> TaskAddResult:
        """Add a pull request task if it does not already exist."""
        if not force:
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

    def add_jira_issue(
        self,
        value: str,
        overrides: TaskOverrides,
        *,
        force: bool = False,
    ) -> TaskAddResult:
        """Add a Jira issue task using issue metadata."""
        if self._jira_client is None:
            raise ValueError("Jira client is not configured")

        code = parse_jira_issue_code(value)
        if code is None:
            raise ValueError("Expected a Jira issue URL or code")

        issue = self._jira_client.get_issue(code)
        url = issue.url

        if url is not None and not force:
            existing = self._notion_client.find_task_by_url(url)
            if existing is not None:
                return TaskAddResult(task=existing, created=False)

        return TaskAddResult(
            task=self._notion_client.create_task(build_jira_task(issue, overrides)),
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
            raise ValueError(f'Task "{task_id}" was not found')
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
        level=TaskLevel.from_value(overrides.level) if overrides.level else default_task_level,
        status=TaskStatus.from_value(overrides.status) if overrides.status else default_task_status,
        until=overrides.until,
        url=overrides.url or default_url,
    )


def build_jira_task(issue: Issue, overrides: TaskOverrides) -> TaskCreate:
    """Build a task payload from Jira issue metadata."""
    issue_fields: dict[str, str] = {}
    for field_name in ("title", "status", "priority"):
        field_value = getattr(issue, field_name)
        if field_value is None:
            raise ValueError(f'Jira issue "{issue.code}" has no {field_name}')
        issue_fields[field_name] = field_value

    return build_task(
        name=issue_fields["title"],
        default_url=issue.url,
        default_task_level=TaskLevel.from_jira_priority(issue_fields["priority"]),
        default_task_status=TaskStatus.from_jira_status(issue_fields["status"]),
        overrides=overrides,
    )
