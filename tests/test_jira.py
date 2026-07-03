import httpx
import pytest

from jira.client import JiraClient
from jira.mock import MockJiraClient
from jira.resources import Issue


def test_issue_exposes_fields_from_raw_payload() -> None:
    """Read derived Jira issue properties from raw payload."""
    issue = Issue(
        raw={
            "key": "PROJ-123",
            "fields": {
                "assignee": {"name": "denis"},
                "labels": ["backend", "urgent"],
                "description": "Fix API timeout",
                "priority": {"name": "Major"},
                "status": {"name": "In Progress"},
                "summary": "Stabilize issue sync",
            },
        }
    )

    assert issue.code == "PROJ-123"
    assert issue.assignee == "denis"
    assert issue.labels == ["backend", "urgent"]
    assert issue.description == "Fix API timeout"
    assert issue.priority == "Major"
    assert issue.status == "In Progress"
    assert issue.summary == "Stabilize issue sync"
    assert issue.title == "Stabilize issue sync"


def test_issue_falls_back_to_url_for_code() -> None:
    """Extract Jira issue key from URL when raw key is missing."""
    issue = Issue(url="https://jira.example.com/rest/api/2/issue/PROJ-123")

    assert issue.code == "PROJ-123"


def test_jira_client_gets_issue() -> None:
    """Fetch a Jira issue over HTTP."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Return a mocked Jira API response."""
        assert request.method == "GET"
        assert request.url.path == "/rest/api/2/issue/PROJ-123"
        return httpx.Response(
            200,
            json={
                "key": "PROJ-123",
                "fields": {
                    "summary": "Stabilize issue sync",
                    "status": {"name": "Done"},
                },
            },
        )

    http_client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://jira.example.com",
    )
    client = JiraClient(http_client, browse_base_url="https://jira.example.com/")

    issue = client.get_issue("PROJ-123")

    assert issue.code == "PROJ-123"
    assert issue.summary == "Stabilize issue sync"
    assert issue.status == "Done"
    assert issue.url == "https://jira.example.com/browse/PROJ-123"


def test_mock_jira_client_returns_issue() -> None:
    """Return a stored Jira issue from the mock client."""
    issue = Issue(raw={"key": "PROJ-123", "fields": {"summary": "Test issue"}})
    client = MockJiraClient([issue])

    result = client.get_issue("PROJ-123")

    assert result == issue


def test_mock_jira_client_raises_for_missing_issue() -> None:
    """Raise an error for a missing Jira issue in the mock client."""
    client = MockJiraClient()

    with pytest.raises(KeyError, match='Jira issue "PROJ-123" was not found'):
        client.get_issue("PROJ-123")
