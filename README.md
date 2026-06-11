# notion-task-tracker

Notion-based task tracker automatization

# Notion task fields

This is how I manage my current task tracker:

- `Task name`: str - task name. Required.
- `Level`: str - task level (Low, Medium, High). Default: `Medium`.
- `Status`: str - task status (TODO, Planning, In Progress, In review, Done). Default: `TODO`.
- `Until`: date - task deadline. Default: `None`.
- `URL`: str - task URL (Github, Jira). Default: `None`.

# CLI Usage

## Configuration

Create `~/.config/notion-task-tracker/config.toml`:

```toml
[notion]
base_url = "https://api.notion.com/v1"
api_token = "<notion-api-token>"
api_version = "2022-06-28"

[database]
id = "<notion-database-id>"
name = "Task Tracker"
```

## Auto-adding tasks

Add task to task tracker with auto-detection algorithm:

```bash
notion-task-tracker add <any>
```

Algorithm:
- If <any> is a link to github pull request - create pull request task
- Otherwise - create regular task and use <any> as a task name

## Pull Request

Add pull request to task tracker in "TODO" state if it doesn't exist with PR link in URL field:

```bash
notion-task-tracker pr https://github.com/example/pull/17
```

# Global CLI params

For each command you can specify the following global CLI params and it will override auto-detection:

- `-n`, `--name`: specify task name and paste it as is
- `-l`, `--level`: specify task level (Low, Medium, High). Accepts shorthand (`l`, `m`, `h`).
- `-s`, `--status`: specify task status (TODO, Planning, In Progress, In review, Done)
- `-u`, `--until`: specify task deadline (format: `YYYY-MM-DD`). Accepts integer values like -1, 0, 1 that represent days offset from today (0 is current day, -1 is yesterday, 1 is tomorrow and so on).
- `-u`, `--url`: specify task URL
