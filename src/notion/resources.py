from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class TaskLevel(StrEnum):
    """Task priority level in the Notion tracker."""

    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


class TaskStatus(StrEnum):
    """Task workflow status in the Notion tracker."""

    TODO = "TODO"
    PLANNING = "Planning"
    IN_PROGRESS = "In progress"
    IN_REVIEW = "In review"
    DONE = "Done"


class NotionConfig(BaseModel):
    """Runtime settings for connecting to the Notion API."""

    base_url: str
    api_token: str
    api_version: str


class DatabaseConfig(BaseModel):
    """Runtime settings for connecting to the Notion task database."""

    id: str
    name: str


class TaskTrackerConfig(BaseModel):
    """Runtime settings for the task tracker application."""

    notion: NotionConfig
    database: DatabaseConfig


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
        return value.strip()

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
