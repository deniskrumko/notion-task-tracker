from datetime import date
from typing import Any

from notion.resources import Task, TaskCreate, TaskLevel, TaskStatus


def extract_plain_text(items: list[dict[str, Any]]) -> str:
    """Extract plain text from Notion rich text fragments."""
    return "".join(item.get("plain_text", "") for item in items).strip()


def database_title(database: dict[str, Any]) -> str:
    """Extract a database title from Notion search data."""
    return extract_plain_text(database.get("title", []))


def task_to_notion_properties(task: TaskCreate) -> dict[str, Any]:
    """Convert a task payload into Notion page properties."""
    properties: dict[str, Any] = {
        "Task name": {
            "title": [
                {
                    "text": {
                        "content": task.name,
                    },
                },
            ],
        },
        "Status": {"status": {"name": task.status.value}},
    }
    if task.level is not None:
        properties["Level"] = {"select": {"name": task.level.value}}
    if task.until is not None:
        properties["Until"] = {"date": {"start": task.until.isoformat()}}
    if task.url is not None:
        properties["URL"] = {"url": task.url}
    return properties


def page_to_task(page: dict[str, Any]) -> Task:
    """Convert a Notion page object into a task."""
    properties = page.get("properties", {})
    return Task(
        id=str(page["id"]),
        name=property_title(properties.get("Task name", {})) or "Untitled",
        level=property_task_level(properties.get("Level", {})),
        status=TaskStatus(property_status_name(properties.get("Status", {})) or TaskStatus.TODO),
        until=property_date(properties.get("Until", {})),
        url=property_url(properties.get("URL", {})),
    )


def property_title(prop: dict[str, Any]) -> str:
    """Extract a title property value."""
    return extract_plain_text(prop.get("title", []))


def property_select_name(prop: dict[str, Any]) -> str:
    """Extract a select property name."""
    return (prop.get("select") or {}).get("name", "")


def property_task_level(prop: dict[str, Any]) -> TaskLevel | None:
    """Extract a task level property value."""
    value = property_select_name(prop)
    if not value:
        return None
    return TaskLevel(value)


def property_status_name(prop: dict[str, Any]) -> str:
    """Extract a status property name."""
    return (prop.get("status") or {}).get("name", "")


def property_date(prop: dict[str, Any]) -> date | None:
    """Extract a date property start value."""
    date_data = prop.get("date") or {}
    value = date_data.get("start")
    if value is None:
        return None
    return date.fromisoformat(value)


def property_url(prop: dict[str, Any]) -> str | None:
    """Extract a URL property value."""
    return prop.get("url") or None
