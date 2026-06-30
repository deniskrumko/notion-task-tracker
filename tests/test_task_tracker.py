import json
from datetime import date
from io import StringIO

import httpx
import pytest
from rich.console import Console

import app.cli as cli_module
from app.cli import (
    CONFIG_PATH,
    build_parser,
    load_config,
    print_task_list,
    print_task_result,
    resolve_view_name,
    task_badges,
)
from notion.client import (
    NotionClient,
    NotionError,
    page_to_task,
    task_to_notion_properties,
    views_api_version,
)
from notion.mock import MockNotionClient
from notion.resources import (
    DatabaseConfig,
    NotionConfig,
    Task,
    TaskCreate,
    TaskLevel,
    TaskStatus,
    TaskTrackerConfig,
    ViewConfig,
)
from task_tracker.client import TaskTrackerClient, build_task
from task_tracker.resources import (
    TaskAddResult,
    TaskOverrides,
    parse_date_offset,
    parse_github_pull_request_url,
)


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

[views.today]
name = "Сегодня"
default = true

[views.sort]
name = "Разобрать"
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.notion.base_url == "https://api.notion.com/v1"
    assert config.notion.api_token == "secret"
    assert config.notion.api_version == "2022-06-28"
    assert config.database.id == "database-id"
    assert config.database.name == "Task Tracker"
    assert config.views["today"].name == "Сегодня"
    assert config.views["today"].default is True
    assert config.views["sort"].name == "Разобрать"


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


def test_add_command_accepts_force_flag() -> None:
    """Parse force flag for auto-detected task creation."""
    args = build_parser().parse_args(["add", "--force", "https://github.com/a/b/pull/1"])

    assert args.command == "add"
    assert args.force is True


def test_pr_command_accepts_force_flag() -> None:
    """Parse force flag for pull request task creation."""
    args = build_parser().parse_args(["pr", "--force", "https://github.com/a/b/pull/1"])

    assert args.command == "pr"
    assert args.force is True


def test_list_command_accepts_view_key() -> None:
    """Parse a list command with a configured view key."""
    args = build_parser().parse_args(["list", "--view", "today"])

    assert args.command == "list"
    assert args.view == "today"
    assert args.all is False


def test_list_command_accepts_all_flag() -> None:
    """Parse a list command that ignores configured views."""
    args = build_parser().parse_args(["list", "--all"])

    assert args.command == "list"
    assert args.all is True


def test_list_command_accepts_id_flag() -> None:
    """Parse a list command that requests task IDs."""
    args = build_parser().parse_args(["list", "-i"])

    assert args.command == "list"
    assert args.id is True


def test_delete_command_accepts_task_ids() -> None:
    """Parse a delete command with task IDs."""
    args = build_parser().parse_args(["delete", "first-id", "second-id"])

    assert args.command == "delete"
    assert args.task_ids == ["first-id", "second-id"]


def test_resolve_view_name_uses_explicit_configured_view() -> None:
    """Resolve an explicit CLI view key from configuration."""
    config = build_config(
        views={
            "today": ViewConfig(name="Сегодня", default=True),
            "sort": ViewConfig(name="Разобрать"),
        }
    )

    assert resolve_view_name(config, "sort", False) == "Разобрать"


def test_resolve_view_name_uses_default_view() -> None:
    """Resolve the default configured view when no CLI view key is supplied."""
    config = build_config(views={"today": ViewConfig(name="Сегодня", default=True)})

    assert resolve_view_name(config, None, False) == "Сегодня"


def test_resolve_view_name_uses_unknown_view_key_as_display_name() -> None:
    """Use an unknown CLI view key as a direct Notion view name."""
    config = build_config(views={"today": ViewConfig(name="Сегодня", default=True)})

    assert resolve_view_name(config, "missing", False) == "missing"


def test_resolve_view_name_ignores_views_for_all_flag() -> None:
    """Return no view when all tasks are requested."""
    config = build_config(views={"today": ViewConfig(name="Сегодня", default=True)})

    assert resolve_view_name(config, "today", True) is None


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
    task = build_task("Ship feature")

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
        default_url="https://github.com/example/repo/pull/17",
        overrides=TaskOverrides(
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
    assert task.status == TaskStatus.PLANNING
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


def test_add_pull_request_force_creates_duplicate_task() -> None:
    """Create a pull request task even when the URL already exists."""
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
    result = client.add_pull_request(
        pull_request,
        TaskOverrides(name="New name"),
        force=True,
    )

    assert result.created is True
    assert result.task.name == "New name"
    assert result.task.url == existing.url
    assert notion_client.tasks == [existing, result.task]


def test_delete_task_removes_existing_task() -> None:
    """Delete an existing task by internal ID."""
    existing = Task(id="task-id", name="Write docs", status=TaskStatus.TODO)
    notion_client = MockNotionClient(tasks=[existing])
    client = TaskTrackerClient(notion_client)

    result = client.delete_task("task-id")

    assert result.task == existing
    assert notion_client.tasks == []


def test_delete_tasks_removes_multiple_existing_tasks() -> None:
    """Delete multiple existing tasks by internal IDs."""
    first = Task(id="first-id", name="Write docs", status=TaskStatus.TODO)
    second = Task(id="second-id", name="Ship feature", status=TaskStatus.TODO)
    notion_client = MockNotionClient(tasks=[first, second])
    client = TaskTrackerClient(notion_client)

    result = client.delete_tasks(["first-id", "second-id"])

    assert result.tasks == [first, second]
    assert notion_client.tasks == []


def test_delete_task_raises_error_for_missing_id() -> None:
    """Raise an error when deleting a missing task ID."""
    client = TaskTrackerClient(MockNotionClient())

    with pytest.raises(ValueError, match='Task "missing" was not found.'):
        client.delete_task("missing")


def test_task_badges_omit_missing_until() -> None:
    """Build badges without an empty until placeholder."""
    task = Task(id="task-id", name="Write docs", status=TaskStatus.TODO)

    badges = task_badges(task)

    assert "No until" not in badges.plain
    assert badges.plain == " TODO "


def test_task_badges_add_space_between_badges() -> None:
    """Build badges with one spacer between styled badge spans."""
    task = Task(
        id="task-id",
        name="Write docs",
        level=TaskLevel.HIGH,
        status=TaskStatus.IN_PROGRESS,
        until=date(2026, 6, 12),
    )

    badges = task_badges(task)

    assert badges.plain == " High   In progress   2026-06-12 "
    assert badges.spans[0].end + 1 == badges.spans[1].start
    assert badges.spans[1].end + 1 == badges.spans[2].start


def test_print_task_list_shows_ids_when_requested(monkeypatch: pytest.MonkeyPatch) -> None:
    """Print task IDs under names when requested."""
    output = StringIO()
    monkeypatch.setattr(
        cli_module,
        "console",
        Console(file=output, force_terminal=False, width=120),
    )
    task = Task(id="task-id", name="Write docs", status=TaskStatus.TODO)

    print_task_list([task], show_ids=True)

    rendered = output.getvalue()
    assert "ID" not in rendered
    assert "task-id" in rendered
    assert "Write docs" in rendered


def test_print_task_result_suggests_force_for_existing_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Print force flag hint for an existing task."""
    output = StringIO()
    monkeypatch.setattr(
        cli_module,
        "console",
        Console(file=output, force_terminal=False, width=120),
    )
    task = Task(id="task-id", name="Write docs", status=TaskStatus.TODO)

    print_task_result(TaskAddResult(task=task, created=False))

    rendered = output.getvalue()
    assert "Task already exists" in rendered
    assert "Use --force to create it anyway" in rendered


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


def test_notion_client_lists_tasks_by_view() -> None:
    """Query a Notion view by display name and return its task pages."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Return mocked Notion API responses."""
        requests.append(request)
        if request.method == "GET" and request.url.path == "/v1/views":
            return httpx.Response(
                200,
                json={"results": [{"object": "view", "id": "view-id"}], "has_more": False},
            )
        if request.method == "GET" and request.url.path == "/v1/views/view-id":
            return httpx.Response(200, json={"id": "view-id", "name": "Сегодня"})
        if request.method == "POST" and request.url.path == "/v1/views/view-id/queries":
            return httpx.Response(
                200,
                json={
                    "id": "query-id",
                    "results": [{"object": "page", "id": "task-id"}],
                    "has_more": False,
                    "next_cursor": None,
                },
            )
        if request.method == "GET" and request.url.path == "/v1/pages/task-id":
            return httpx.Response(200, json=notion_page("task-id", "Write tests"))
        if request.method == "DELETE" and request.url.path == "/v1/views/view-id/queries/query-id":
            return httpx.Response(200, json={"id": "query-id", "deleted": True})
        return httpx.Response(404, json={"message": "not found"})

    http_client = httpx.Client(
        base_url="https://api.notion.com/v1",
        transport=httpx.MockTransport(handler),
    )
    client = NotionClient(http_client, "database-id", "2022-06-28")

    tasks = client.list_tasks_by_view("Сегодня")

    assert [task.name for task in tasks] == ["Write tests"]
    assert [(request.method, request.url.path) for request in requests] == [
        ("GET", "/v1/views"),
        ("GET", "/v1/views/view-id"),
        ("POST", "/v1/views/view-id/queries"),
        ("GET", "/v1/pages/task-id"),
        ("DELETE", "/v1/views/view-id/queries/query-id"),
    ]
    assert [request.headers["Notion-Version"] for request in requests] == [
        "2025-09-03",
        "2025-09-03",
        "2025-09-03",
        "2022-06-28",
        "2025-09-03",
    ]


def test_notion_client_raises_error_for_missing_view() -> None:
    """Raise an error when a Notion view display name is missing."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Return mocked Notion API responses."""
        if request.method == "GET" and request.url.path == "/v1/views":
            return httpx.Response(
                200,
                json={"results": [{"object": "view", "id": "view-id"}], "has_more": False},
            )
        if request.method == "GET" and request.url.path == "/v1/views/view-id":
            return httpx.Response(200, json={"id": "view-id", "name": "Сегодня"})
        return httpx.Response(404, json={"message": "not found"})

    http_client = httpx.Client(
        base_url="https://api.notion.com/v1",
        transport=httpx.MockTransport(handler),
    )
    client = NotionClient(http_client, "database-id", "2022-06-28")

    with pytest.raises(NotionError, match='View "missing" was not found.'):
        client.list_tasks_by_view("missing")


def test_notion_client_deletes_task_by_id() -> None:
    """Archive a Notion page by internal task ID for older API versions."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Return mocked Notion API responses."""
        requests.append(request)
        if request.method == "PATCH" and request.url.path == "/v1/pages/task-id":
            payload = json.loads(request.content)
            assert payload == {"archived": True}
            return httpx.Response(200, json=notion_page("task-id", "Write docs"))
        return httpx.Response(404, json={"message": "not found"})

    http_client = httpx.Client(
        base_url="https://api.notion.com/v1",
        transport=httpx.MockTransport(handler),
    )
    client = NotionClient(http_client, "database-id", "2022-06-28")

    task = client.delete_task("task-id")

    assert task is not None
    assert task.id == "task-id"
    assert task.name == "Write docs"
    assert [(request.method, request.url.path) for request in requests] == [
        ("PATCH", "/v1/pages/task-id"),
    ]


def test_notion_client_deletes_task_by_id_for_new_api() -> None:
    """Move a Notion page to trash by internal task ID for newer API versions."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Return mocked Notion API responses."""
        requests.append(request)
        if request.method == "PATCH" and request.url.path == "/v1/pages/task-id":
            payload = json.loads(request.content)
            assert payload == {"in_trash": True}
            return httpx.Response(200, json=notion_page("task-id", "Write docs"))
        return httpx.Response(404, json={"message": "not found"})

    http_client = httpx.Client(
        base_url="https://api.notion.com/v1",
        transport=httpx.MockTransport(handler),
    )
    client = NotionClient(http_client, "database-id", "2026-03-11")

    task = client.delete_task("task-id")

    assert task is not None
    assert task.id == "task-id"
    assert task.name == "Write docs"
    assert [(request.method, request.url.path) for request in requests] == [
        ("PATCH", "/v1/pages/task-id"),
    ]


def test_notion_client_returns_none_when_deleted_task_is_missing() -> None:
    """Return no task when a deleted task ID is missing."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Return mocked Notion API responses."""
        return httpx.Response(404, json={"message": "not found"})

    http_client = httpx.Client(
        base_url="https://api.notion.com/v1",
        transport=httpx.MockTransport(handler),
    )
    client = NotionClient(http_client, "database-id", "2022-06-28")

    assert client.delete_task("missing") is None


def test_notion_client_returns_none_when_deleted_task_is_archived() -> None:
    """Return no task when a deleted task is already archived."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Return mocked Notion API responses."""
        return httpx.Response(
            400,
            json={"message": "Can't edit block that is archived. You must unarchive it."},
        )

    http_client = httpx.Client(
        base_url="https://api.notion.com/v1",
        transport=httpx.MockTransport(handler),
    )
    client = NotionClient(http_client, "database-id", "2026-03-11")

    assert client.delete_task("archived") is None


def test_notion_client_creates_task_in_data_source_for_new_api() -> None:
    """Create a task under the first database data source for new Notion APIs."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Return mocked Notion API responses."""
        requests.append(request)
        if request.method == "GET" and request.url.path == "/v1/databases/database-id":
            return httpx.Response(
                200,
                json={"id": "database-id", "data_sources": [{"id": "data-source-id"}]},
            )
        if request.method == "POST" and request.url.path == "/v1/pages":
            payload = json.loads(request.content)
            assert payload["parent"] == {"data_source_id": "data-source-id"}
            return httpx.Response(200, json=notion_page("task-id", "Write tests"))
        return httpx.Response(404, json={"message": "not found"})

    http_client = httpx.Client(
        base_url="https://api.notion.com/v1",
        transport=httpx.MockTransport(handler),
    )
    client = NotionClient(http_client, "database-id", "2026-03-11")

    task = client.create_task(TaskCreate(name="Write tests"))

    assert task.name == "Write tests"
    assert [(request.method, request.url.path) for request in requests] == [
        ("GET", "/v1/databases/database-id"),
        ("POST", "/v1/pages"),
    ]


def test_views_api_version_keeps_newer_configured_version() -> None:
    """Keep a configured Notion API version when it already supports views."""
    assert views_api_version("2026-03-11") == "2026-03-11"


def build_config(views: dict[str, ViewConfig] | None = None) -> TaskTrackerConfig:
    """Build a test task tracker configuration."""
    return TaskTrackerConfig(
        notion=NotionConfig(
            base_url="https://api.notion.com/v1",
            api_token="secret",
            api_version="2025-09-03",
        ),
        database=DatabaseConfig(id="database-id", name="Task Tracker"),
        views=views or {},
    )


def notion_page(page_id: str, name: str) -> dict[str, object]:
    """Build a minimal Notion page object for tests."""
    return {
        "id": page_id,
        "properties": {
            "Task name": {"title": [{"plain_text": name}]},
            "Level": {"select": {"name": "Medium"}},
            "Status": {"status": {"name": "TODO"}},
        },
    }
