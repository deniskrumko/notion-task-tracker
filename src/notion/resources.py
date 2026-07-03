from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

from jira.resources import JiraConfig


class TaskLevel(StrEnum):
    """Task priority level in the Notion tracker."""

    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"

    @classmethod
    def from_value(cls, value: str) -> "TaskLevel":
        """Parse a task level from CLI input."""
        normalized = value.strip().lower()
        if normalized:
            for level in cls:
                if level.value.lower().startswith(normalized):
                    return level

        allowed = ", ".join(level.value for level in cls)
        raise ValueError(f"Invalid level {value!r}. Allowed values: {allowed}")

    @classmethod
    def from_jira_priority(cls, priority: str) -> "TaskLevel":
        """Map a Jira priority name to a task level."""
        normalized = priority.strip().lower()

        priority_patterns: dict[TaskLevel, tuple[str, ...]] = {
            cls.LOW: ("минор", "тривиал", "low", "низк", "minor"),
            cls.MEDIUM: ("medium", "основной", "main", "major"),
            cls.HIGH: ("крит", "блок", "high", "crit", "block"),
        }
        for task_level, patterns in priority_patterns.items():
            if any(pattern in normalized for pattern in patterns):
                return task_level

        allowed = ", ".join(level.value for level in cls)
        raise ValueError(f"Invalid Jira priority {priority!r}. Allowed task levels: {allowed}")


class TaskStatus(StrEnum):
    """Task workflow status in the Notion tracker."""

    TODO = "TODO"
    PLANNING = "Planning"
    IN_PROGRESS = "In progress"
    IN_REVIEW = "In review"
    IN_TEST = "In test"
    DONE = "Done"

    @classmethod
    def from_value(cls, value: str) -> "TaskStatus":
        """Parse a task status from CLI input."""
        value = value.strip().lower()

        shortcuts: dict[str, TaskStatus] = {
            "t": cls.TODO,
            "td": cls.TODO,
            "p": cls.PLANNING,
            "ip": cls.IN_PROGRESS,
            "ir": cls.IN_REVIEW,
            "it": cls.IN_TEST,
            "test": cls.IN_TEST,
            "d": cls.DONE,
        }

        if value in shortcuts:
            return shortcuts[value]

        for status in cls:
            if status.value.lower() == value:
                return status

        allowed = ", ".join(status.value for status in cls)
        raise ValueError(f"Invalid status {value!r}. Allowed values: {allowed}")

    @classmethod
    def from_jira_status(cls, status: str) -> "TaskStatus":
        """Map a Jira status name to a task status."""
        normalized = status.strip().lower()

        status_patterns: dict[TaskStatus, tuple[str, ...]] = {
            cls.TODO: ("open", "открыт"),
            cls.IN_PROGRESS: ("progress", "работ"),
            cls.IN_REVIEW: ("review", "ревью"),
            cls.IN_TEST: ("test", "тест", "ready", "готово"),
            cls.DONE: ("close", "закрыт"),
        }
        for task_status, patterns in status_patterns.items():
            if any(pattern in normalized for pattern in patterns):
                return task_status

        allowed = ", ".join(status.value for status in cls)
        raise ValueError(f"Invalid Jira status {status!r}. Allowed task statuses: {allowed}")


class NotionConfig(BaseModel):
    """Runtime settings for connecting to the Notion API."""

    base_url: str
    api_token: str
    api_version: str


class DatabaseConfig(BaseModel):
    """Runtime settings for connecting to the Notion task database."""

    id: str
    name: str


class ViewConfig(BaseModel):
    """Runtime settings for a configured Notion database view."""

    name: str
    default: bool = False


class TaskTrackerConfig(BaseModel):
    """Runtime settings for the task tracker application."""

    notion: NotionConfig
    database: DatabaseConfig
    jira: JiraConfig | None = None
    views: dict[str, ViewConfig] = Field(default_factory=dict)


class TaskCreate(BaseModel):
    """Task payload accepted by the task tracker."""

    name: str = Field(min_length=1)
    level: TaskLevel | None = None
    status: TaskStatus = TaskStatus.TODO
    until: date | None = None
    url: str | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        """Normalize task name before validation."""
        value = value.strip()

        # Capitalize first letter if lowercase
        if value[0].islower():
            value = value[0].upper() + value[1:]

        return value

    @field_validator("url")
    @classmethod
    def strip_url(cls, value: str | None) -> str | None:
        """Normalize optional task URL before validation."""
        if value is None:
            return None

        value = value.strip()
        return value or None


class Task(BaseModel):
    """Task stored in the Notion task tracker."""

    id: str
    name: str
    level: TaskLevel | None = None
    status: TaskStatus
    until: date | None = None
    url: str | None = None
