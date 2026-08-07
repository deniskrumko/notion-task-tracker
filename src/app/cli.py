import argparse
import tomllib
from contextlib import nullcontext
from pathlib import Path

from rich.console import Console, Group
from rich.table import Table
from rich.text import Text

from jira.client import JiraClient
from notion.client import NotionClient, NotionError
from notion.resources import Task, TaskTrackerConfig
from task_tracker.client import TaskTrackerClient
from task_tracker.resources import (
    TaskAddResult,
    TaskDeleteResult,
    TaskOverrides,
    parse_date_offset,
    parse_github_pull_request_url,
)

console = Console()
error_console = Console(stderr=True)
CONFIG_PATH = Path("~/.config/notion-task-tracker/config.toml")


def main() -> int:
    """Run the task tracker CLI."""
    parser = build_parser()
    args = parser.parse_args()

    try:
        config = load_config()
        with NotionClient.from_config(config) as notion_client:
            jira_context = (
                JiraClient.from_config(config) if args.command == "jira" else nullcontext()
            )
            with jira_context as jira_client:
                task_tracker_client = TaskTrackerClient(notion_client, jira_client)
                result = run_command(task_tracker_client, args, config)
    except (NotionError, ValueError) as exc:
        error_console.print(str(exc), style="bold red")
        return 1

    print_command_result(result, show_ids=getattr(args, "id", False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser."""
    parser = argparse.ArgumentParser(prog="notion-task-tracker")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add", help="Add task with auto-detection")
    add_common_flags(add_parser)
    add_parser.add_argument("value", nargs="+")

    today_parser = subparsers.add_parser("today", help="Add task due today")
    add_common_flags(today_parser)
    today_parser.add_argument("value", nargs="+")
    today_parser.set_defaults(until="today")

    add_common_flags(subparsers.add_parser("pr", help="Add GitHub pull request task"))
    subparsers.choices["pr"].add_argument("url")

    add_common_flags(subparsers.add_parser("jira", help="Add Jira issue task"))
    subparsers.choices["jira"].add_argument("value")

    delete_parser = subparsers.add_parser("delete", help="Delete task by internal ID")
    delete_parser.add_argument("task_ids", nargs="+")

    list_parser = subparsers.add_parser("list", help="List tasks")
    list_parser.add_argument("--view")
    list_parser.add_argument("--all", action="store_true")
    list_parser.add_argument("-i", "--id", action="store_true")

    return parser


def add_common_flags(parser: argparse.ArgumentParser) -> None:
    """Add task override flags to a subcommand parser."""
    parser.add_argument("-n", "--name")
    parser.add_argument("-l", "--level")
    parser.add_argument("-s", "--status")
    parser.add_argument(
        "-u",
        "--until",
        help="ISO date, day offset, or named date (for example: today, tm, nw)",
    )
    parser.add_argument("--url")
    parser.add_argument("--force", action="store_true")


def load_config(path: Path = CONFIG_PATH) -> TaskTrackerConfig:
    """Load task tracker configuration from a TOML file."""
    expanded_path = path.expanduser()
    if not expanded_path.exists():
        raise ValueError(f"Config is not set: {path}")

    with expanded_path.open("rb") as file:
        return TaskTrackerConfig.model_validate(tomllib.load(file))


def run_command(
    task_tracker_client: TaskTrackerClient,
    args: argparse.Namespace,
    config: TaskTrackerConfig,
) -> TaskAddResult | TaskDeleteResult | list[Task]:
    """Execute the requested CLI command."""
    if args.command in {"add", "today"}:
        overrides = parse_task_overrides(args)
        return task_tracker_client.add_auto(" ".join(args.value), overrides, force=args.force)

    if args.command == "pr":
        overrides = parse_task_overrides(args)
        pull_request = parse_github_pull_request_url(args.url)
        if pull_request is None:
            raise ValueError("Expected a GitHub pull request URL")
        return task_tracker_client.add_pull_request(pull_request, overrides, force=args.force)

    if args.command == "jira":
        overrides = parse_task_overrides(args)
        return task_tracker_client.add_jira_issue(args.value, overrides, force=args.force)

    if args.command == "delete":
        return task_tracker_client.delete_tasks(args.task_ids)

    if args.command == "list":
        return task_tracker_client.list_tasks(resolve_view_name(config, args.view, args.all))

    raise ValueError(f"Unsupported command: {args.command}")


def parse_task_overrides(args: argparse.Namespace) -> TaskOverrides:
    """Parse task override fields from CLI arguments."""
    return TaskOverrides(
        name=args.name,
        level=args.level,
        status=args.status,
        until=parse_date_offset(args.until) if args.until else None,
        url=args.url,
    )


def resolve_view_name(
    config: TaskTrackerConfig, view_key: str | None, all_tasks: bool
) -> str | None:
    """Resolve a CLI view key into a Notion view display name."""
    if all_tasks:
        return None
    if view_key is not None:
        view = config.views.get(view_key)
        return view.name if view else view_key

    for view in config.views.values():
        if view.default:
            return view.name

    return None


def print_command_result(
    result: TaskAddResult | TaskDeleteResult | list[Task], show_ids: bool = False
) -> None:
    """Print a command result."""
    if isinstance(result, list):
        print_task_list(result, show_ids)
    elif isinstance(result, TaskDeleteResult):
        print_task_delete_result(result)
    else:
        print_task_result(result)


def print_task_result(result: TaskAddResult) -> None:
    """Print task operation result."""
    if result.created:
        console.print("✅  Task created\n", style="bold green")
    else:
        console.print(
            "⚠️  Task already exists. Use --force to create it anyway.\n",
            style="bold yellow",
        )
    console.print(task_lines(result.task))


def print_task_delete_result(result: TaskDeleteResult) -> None:
    """Print task deletion result."""
    message = "Task deleted" if len(result.tasks) == 1 else "Tasks deleted"
    console.print(f"{message}\n", style="bold green")
    for task in result.tasks:
        console.print(task_lines(task))


def print_task_list(tasks: list[Task], show_ids: bool = False) -> None:
    """Print task list result."""
    if not tasks:
        console.print("No tasks found", style="bold yellow")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Task", overflow="fold")
    table.add_column("Details", no_wrap=True)
    table.add_column("URL", overflow="fold")

    for task in tasks:
        table.add_row(task_name_cell(task, show_ids), task_badges(task), task.url or "")

    console.print(table)


def task_name_cell(task: Task, show_id: bool = False) -> Text:
    """Build task list name cell."""
    text = Text(task.name, style="bold")
    if show_id:
        text.append("\n")
        text.append(task.id, style="grey50")
    return text


def task_lines(task: Task) -> Group:
    """Build task output lines."""
    rows = [
        Text(task.name, style="bold"),
        task_badges(task),
    ]
    if task.url:
        rows.append(Text(task.url, style=f"grey50 link {task.url}"))
    return Group(*rows)


def task_badges(task: Task) -> Text:
    """Build task metadata badges."""
    badges = Text()
    if task.level is not None:
        append_badge(badges, task.level.value, level_style(task.level.value))
    append_badge(badges, task.status.value, status_style(task.status.value))
    if task.until is not None:
        append_badge(badges, task.until.isoformat(), "bold black on magenta")
    return badges


def append_badge(text: Text, label: str, style: str) -> None:
    """Append a styled badge to text."""
    if text:
        text.append(" ")
    text.append(f" {label} ", style=style)


def level_style(level: str) -> str:
    """Return badge style for a task level."""
    return {
        "Low": "bold black on green",
        "Medium": "bold black on yellow",
        "High": "bold black on red",
    }.get(level, "bold white on cyan")


def status_style(status: str) -> str:
    """Return badge style for a task status."""
    return {
        "TODO": "bold white on grey23",
        "Planning": "bold black on magenta",
        "In progress": "bold white on blue",
        "In review": "bold black on yellow",
        "In test": "bold black on cyan",
        "Done": "bold black on green",
    }.get(status, "bold white on cyan")


if __name__ == "__main__":
    raise SystemExit(main())
