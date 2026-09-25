from datetime import datetime, time
from enum import Enum, IntEnum
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class Unit(Enum):
    SECONDS = "seconds"
    MINUTES = "minutes"
    HOURS = "hours"
    DAYS = "days"


class Weekday(IntEnum):
    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6


class WorkingHours:
    """A recurring local-time window in which a scheduled task may run."""

    def __init__(self, start: time, end: time, timezone: str = "UTC", weekdays: Optional[frozenset[Weekday]] = None) -> None:
        self.start = start
        self.end = end
        self.timezone = timezone
        self.weekdays = weekdays if weekdays is not None else frozenset({Weekday.MONDAY, Weekday.TUESDAY, Weekday.WEDNESDAY, Weekday.THURSDAY, Weekday.FRIDAY})
        self._validate()

    def _validate(self) -> None:
        if self.start.tzinfo is not None or self.end.tzinfo is not None:
            raise ValueError("Working-hours start and end must be timezone-naive times")
        if self.start == self.end:
            raise ValueError("Working-hours start and end must be different")

        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as error:
            raise ValueError(f"Unknown working-hours timezone: {self.timezone}") from error

        try:
            weekdays = frozenset(Weekday(day) for day in self.weekdays)
        except ValueError as error:
            raise ValueError("Working-hours weekdays must contain valid Weekday values") from error
        if not weekdays:
            raise ValueError("Working-hours weekdays cannot be empty")
        self.weekdays = weekdays

    def allows(self, moment: datetime) -> bool:
        """Return whether an aware instant falls within this working window."""
        if moment.tzinfo is None:
            raise ValueError("WorkingHours.allows requires a timezone-aware datetime")

        local = moment.astimezone(ZoneInfo(self.timezone))
        local_time = local.time()
        weekday = Weekday(local.weekday())

        if self.start < self.end:
            return weekday in self.weekdays and self.start <= local_time < self.end

        # Overnight windows belong to the day on which they open. For example,
        # Friday 22:00-06:00 includes early Saturday morning.
        if local_time >= self.start:
            opening_day = weekday
        elif local_time < self.end:
            opening_day = Weekday((weekday - 1) % 7)
        else:
            return False
        return opening_day in self.weekdays
