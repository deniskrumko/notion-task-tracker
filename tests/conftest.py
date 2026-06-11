import pytest

from notion.mock import MockNotionClient


@pytest.fixture
def mock_notion_client() -> MockNotionClient:
    """Create an empty mock Notion client."""
    return MockNotionClient()
