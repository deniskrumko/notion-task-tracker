import argparse
import tomllib
from pathlib import Path

from rich.console import Console, Group
from rich.text import Text

from notion.client import NotionClient, NotionError
from notion.resources import Task, TaskTrackerConfig
from task_tracker.client import TaskTrackerClient
from task_tracker.resources import (
    TaskAddResult,
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
        overrides = TaskOverrides(
            name=args.name,
            level=args.level,
            status=args.status,
            until=parse_date_offset(args.until) if args.until else None,
            url=args.url,
        )

        with NotionClient.from_config(config) as notion_client:
            task_tracker_client = TaskTrackerClient(notion_client)
            result = run_command(task_tracker_client, args, overrides)
    except (NotionError, ValueError) as exc:
        error_console.print(str(exc), style="bold red")
        return 1

    print_task_result(result)
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser."""
    parser = argparse.ArgumentParser(prog="notion-task-tracker")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_common_flags(subparsers.add_parser("add", help="Add task with auto-detection"))
    subparsers.choices["add"].add_argument("value", nargs="+")

    add_common_flags(subparsers.add_parser("pr", help="Add GitHub pull request task"))
    subparsers.choices["pr"].add_argument("url")

    return parser


def add_common_flags(parser: argparse.ArgumentParser) -> None:
    """Add task override flags to a subcommand parser."""
    parser.add_argument("-n", "--name")
    parser.add_argument("-l", "--level")
    parser.add_argument("-s", "--status")
    parser.add_argument("-u", "--until")
    parser.add_argument("--url")


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
    overrides: TaskOverrides,
) -> TaskAddResult:
    """Execute the requested CLI command."""
    if args.command == "add":
        return task_tracker_client.add_auto(" ".join(args.value), overrides)

    if args.command == "pr":
        pull_request = parse_github_pull_request_url(args.url)
        if pull_request is None:
            raise ValueError("Expected a GitHub pull request URL.")
        return task_tracker_client.add_pull_request(pull_request, overrides)

    raise ValueError(f"Unsupported command: {args.command}")


def print_task_result(result: TaskAddResult) -> None:
    """Print task operation result."""
    if result.created:
        console.print("✅  Task created\n", style="bold green")
    else:
        console.print("⚠️  Task already exists\n", style="bold yellow")
    console.print(task_lines(result.task))


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
    append_badge(
        badges,
        task.until.isoformat() if task.until else "No until",
        "bold black on magenta",
    )
    return badges


def append_badge(text: Text, label: str, style: str) -> None:
    """Append a styled badge to text."""
    text.append(f" {label} ", style=style)


def level_style(level: str) -> str:
    """Return badge style for a task level."""
    return {
        "Low": "bold white on green",
        "Medium": "bold black on yellow",
        "High": "bold white on red",
    }.get(level, "bold white on cyan")


def status_style(status: str) -> str:
    """Return badge style for a task status."""
    return {
        "TODO": "bold white on grey23",
        "Planning": "bold white on magenta",
        "In progress": "bold white on blue",
        "In review": "bold black on yellow",
        "Done": "bold white on green",
    }.get(status, "bold white on cyan")


if __name__ == "__main__":
    raise SystemExit(main())
