from jira.client import ABCJiraClient
from jira.resources import Issue


class MockJiraClient(ABCJiraClient):
    """In-memory Jira client for tests and local dry runs."""

    def __init__(self, issues: list[Issue] | None = None) -> None:
        """Initialize class instance."""
        self._issues = {issue.code: issue for issue in issues or []}

    def get_issue(self, code: str) -> Issue:
        """Return a Jira issue by key."""
        try:
            return self._issues[code]
        except KeyError as error:
            raise KeyError(f'Jira issue "{code}" was not found') from error
