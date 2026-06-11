from itertools import count

from notion.client import ABCNotionClient
from notion.resources import Task, TaskCreate


class MockNotionClient(ABCNotionClient):
    """In-memory Notion client for tests and local dry runs."""

    def __init__(self, tasks: list[Task] | None = None) -> None:
        """Initialize class instance."""
        self.tasks = list(tasks or [])
        self._ids = count(len(self.tasks) + 1)

    def create_task(self, task: TaskCreate) -> Task:
        """Create a task in the tracker."""
        created = Task(
            id=str(next(self._ids)),
            name=task.name,
            level=task.level,
            status=task.status,
            until=task.until,
            url=task.url,
        )
        self.tasks.append(created)
        return created

    def find_task_by_url(self, url: str) -> Task | None:
        """Find a task by URL field."""
        return next((task for task in self.tasks if task.url == url), None)
