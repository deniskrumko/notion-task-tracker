from datetime import date

import pytest

from app.cli import CONFIG_PATH, build_parser, load_config
from notion.client import page_to_task, task_to_notion_properties
from notion.mock import MockNotionClient
from notion.resources import Task, TaskCreate, TaskLevel, TaskStatus
from task_tracker.client import TaskTrackerClient, build_task
from task_tracker.resources import TaskOverrides, parse_date_offset, parse_github_pull_request_url


def test_parse_github_pull_request_url() -> None:
    """Parse a valid GitHub pull request URL."""
    pull_request = parse_github_pull_request_url("https://github.com/example/repo/pull/17")

    assert pull_request is not None
    assert pull_request.owner == "example"
    assert pull_request.repo == "repo"
    assert pull_request.number == 17
    assert pull_request.task_name == "PR #17 example/repo"


def test_load_config_reads_toml_file(tmp_path) -> None:
    """Load application configuration from a TOML file."""
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[notion]
base_url = "https://api.notion.com/v1"
api_token = "secret"
api_version = "2022-06-28"

[database]
id = "database-id"
name = "Task Tracker"
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.notion.base_url == "https://api.notion.com/v1"
    assert config.notion.api_token == "secret"
    assert config.notion.api_version == "2022-06-28"
    assert config.database.id == "database-id"
    assert config.database.name == "Task Tracker"


def test_load_config_requires_config_file(tmp_path) -> None:
    """Raise an error when the configuration file is missing."""
    config_path = tmp_path / "missing.toml"

    with pytest.raises(ValueError, match=f"Config is not set: {config_path}"):
        load_config(config_path)


def test_default_config_path() -> None:
    """Keep the default configuration path fixed."""
    assert CONFIG_PATH.as_posix() == "~/.config/notion-task-tracker/config.toml"


def test_add_command_accepts_unquoted_task_name() -> None:
    """Parse unquoted multi-word task names."""
    args = build_parser().parse_args(["add", "hello", "world"])

    assert args.command == "add"
    assert args.value == ["hello", "world"]


def test_parse_self_hosted_github_pull_request_url() -> None:
    """Parse a self-hosted GitHub pull request URL."""
    pull_request = parse_github_pull_request_url(
        "https://github.kolesa-team.org/ml/kolesa-rec-sys/pull/17"
    )

    assert pull_request is not None
    assert pull_request.owner == "ml"
    assert pull_request.repo == "kolesa-rec-sys"
    assert pull_request.number == 17
    assert pull_request.task_name == "PR #17 ml/kolesa-rec-sys"


def test_parse_gitlab_merge_request_url() -> None:
    """Parse a GitLab merge request URL."""
    pull_request = parse_github_pull_request_url(
        "https://gitlab.example.com/ml/platform/kolesa-rec-sys/-/merge_requests/17"
    )

    assert pull_request is not None
    assert pull_request.owner == "ml/platform"
    assert pull_request.repo == "kolesa-rec-sys"
    assert pull_request.number == 17
    assert pull_request.task_name == "PR #17 ml/platform/kolesa-rec-sys"


def test_parse_github_pull_request_url_rejects_non_pr_url() -> None:
    """Reject non pull request URLs."""
    assert parse_github_pull_request_url("https://github.com/example/repo/issues/17") is None
    assert parse_github_pull_request_url("plain task") is None


def test_parse_date_offset_accepts_iso_date() -> None:
    """Parse an ISO date value."""
    assert parse_date_offset("2026-06-11") == date(2026, 6, 11)


def test_parse_date_offset_accepts_relative_zero() -> None:
    """Parse a relative date offset."""
    assert parse_date_offset("0") == date.today()


def test_build_task_applies_defaults() -> None:
    """Build a regular task with default fields."""
    task = build_task("Ship feature", None, TaskOverrides())

    assert task == TaskCreate(
        name="Ship feature",
        level=None,
        status=TaskStatus.TODO,
        until=None,
        url=None,
    )


def test_build_task_applies_overrides() -> None:
    """Build a task with CLI overrides."""
    task = build_task(
        "Default",
        "https://github.com/example/repo/pull/17",
        TaskOverrides(
            name="Review API",
            level="h",
            status="In Progress",
            until=date(2026, 6, 12),
            url="https://jira.example/TASK-1",
        ),
    )

    assert task.name == "Review API"
    assert task.level == TaskLevel.HIGH
    assert task.status == TaskStatus.IN_PROGRESS
    assert task.until == date(2026, 6, 12)
    assert task.url == "https://jira.example/TASK-1"


def test_task_to_notion_properties_omits_empty_level() -> None:
    """Convert task payload without an empty level property."""
    properties = task_to_notion_properties(TaskCreate(name="Ship feature"))

    assert "Level" not in properties


def test_page_to_task_accepts_empty_level() -> None:
    """Convert a Notion page with an empty level."""
    task = page_to_task(
        {
            "id": "task-id",
            "properties": {
                "Task name": {
                    "title": [
                        {
                            "plain_text": "Review PR",
                        },
                    ],
                },
                "Level": {"select": None},
                "Status": {"status": {"name": "TODO"}},
            },
        }
    )

    assert task.level is None


def test_add_auto_creates_regular_task(mock_notion_client: MockNotionClient) -> None:
    """Create a regular task for non pull request input."""
    client = TaskTrackerClient(mock_notion_client)

    result = client.add_auto("Write docs", TaskOverrides(level="low"))
    task = result.task

    assert result.created is True
    assert task.name == "Write docs"
    assert task.level == TaskLevel.LOW
    assert task.url is None
    assert mock_notion_client.tasks == [task]


def test_add_auto_creates_pull_request_task(mock_notion_client: MockNotionClient) -> None:
    """Create a pull request task for a GitHub PR URL."""
    client = TaskTrackerClient(mock_notion_client)

    result = client.add_auto("https://github.com/example/repo/pull/17", TaskOverrides())
    task = result.task

    assert result.created is True
    assert task.name == "PR #17 example/repo"
    assert task.status == TaskStatus.TODO
    assert task.url == "https://github.com/example/repo/pull/17"


def test_add_pull_request_returns_existing_task() -> None:
    """Return an existing task when pull request URL already exists."""
    existing = Task(
        id="existing",
        name="Existing PR",
        level=TaskLevel.MEDIUM,
        status=TaskStatus.TODO,
        url="https://github.com/example/repo/pull/17",
    )
    notion_client = MockNotionClient(tasks=[existing])
    client = TaskTrackerClient(notion_client)
    pull_request = parse_github_pull_request_url(existing.url or "")

    assert pull_request is not None
    result = client.add_pull_request(pull_request, TaskOverrides(name="New name"))

    assert result.created is False
    assert result.task == existing
    assert notion_client.tasks == [existing]


def test_page_to_task_accepts_notion_in_progress_status() -> None:
    """Convert a Notion page with an in-progress status."""
    task = page_to_task(
        {
            "id": "task-id",
            "properties": {
                "Task name": {
                    "title": [
                        {
                            "plain_text": "Review PR",
                        },
                    ],
                },
                "Level": {"select": {"name": "Medium"}},
                "Status": {"status": {"name": "In progress"}},
            },
        }
    )

    assert task.status == TaskStatus.IN_PROGRESS


def test_invalid_level_raises_error() -> None:
    """Raise an error for unsupported task level."""
    with pytest.raises(ValueError, match="Invalid level"):
        build_task("Task", None, TaskOverrides(level="urgent"))
