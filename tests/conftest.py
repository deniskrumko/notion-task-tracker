import pytest

from jira.mock import MockJiraClient
from jira.resources import Issue
from notion.mock import MockNotionClient


@pytest.fixture
def mock_notion_client() -> MockNotionClient:
    """Create an empty mock Notion client."""
    return MockNotionClient()


@pytest.fixture
def mock_jira_client() -> MockJiraClient:
    """Create a mock Jira client with one issue."""
    return MockJiraClient(
        [
            Issue(
                raw={
                    "key": "ML-2100",
                    "fields": {
                        "summary": "Sync model registry",
                        "status": {"name": "Code Review"},
                        "priority": {"name": "Major"},
                    },
                },
                url="https://jira.kolesa-team.org/browse/ML-2100",
            )
        ]
    )
