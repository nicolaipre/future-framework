import asyncio
import random

from datetime import datetime, timedelta, timezone as datetime_timezone
from typing import Callable, Optional

from future.logger import log
from future.scheduling import Unit, Weekday, WorkingHours

__all__ = ["CronScheduler", "ScheduledTask", "Unit", "Weekday", "WorkingHours"]


def _as_utc(moment: datetime) -> datetime:
    """Normalize datetimes for safe comparison and interval arithmetic."""
    if moment.tzinfo is None:
        moment = moment.astimezone()
    return moment.astimezone(datetime_timezone.utc)


class ScheduledTask:
    """Represents a scheduled task with its timing configuration."""

    def __init__(self, task, now: Optional[datetime] = None) -> None:
        self.task = task
        self.name = task.name
        self.interval = task.interval
        self.unit = task.unit
        self.start_time = _as_utc(task.start_time) if task.start_time is not None else _as_utc(now or datetime.now(datetime_timezone.utc))
        self.jitter = task.jitter
        self.working_hours = getattr(task, "working_hours", None)
        if self.working_hours is not None and not isinstance(self.working_hours, WorkingHours):
            raise TypeError("task.working_hours must be a WorkingHours instance or None")
        self.last_run: Optional[datetime] = None
        self.next_run: Optional[datetime] = None
        self.running = False

        self.calculate_next_run()

    def calculate_next_run(self) -> None:
        """Calculate when this task should run next."""
        if self.last_run is None:
            self.next_run = self.start_time
        else:
            if self.unit == Unit.SECONDS:
                self.next_run = self.last_run + timedelta(seconds=self.interval)
            elif self.unit == Unit.MINUTES:
                self.next_run = self.last_run + timedelta(minutes=self.interval)
            elif self.unit == Unit.HOURS:
                self.next_run = self.last_run + timedelta(hours=self.interval)
            elif self.unit == Unit.DAYS:
                self.next_run = self.last_run + timedelta(days=self.interval)
        if self.next_run is not None and self.jitter and self.jitter > 0:
            self.next_run = self.next_run + timedelta(seconds=random.uniform(0, self.jitter))

    def is_due(self, now: datetime) -> bool:
        """Return whether the task is due and permitted to run now."""
        now = _as_utc(now)
        if self.running or self.next_run is None or now < self.next_run:
            return False
        return self.working_hours is None or self.working_hours.allows(now)


class CronScheduler:
    """A cron-like scheduler for running background tasks."""

    def __init__(self, clock: Optional[Callable[[], datetime]] = None) -> None:
        self.tasks: dict[str, ScheduledTask] = {}
        self.running = False
        self.check_interval = 1.0  # Check every second for tasks to run
        self._clock = clock or (lambda: datetime.now(datetime_timezone.utc))

    def _now(self) -> datetime:
        return _as_utc(self._clock())

    def add_task(self, task) -> None:
        if task.interval is None or task.unit is None or not task.name:
            log.warning(f"Skipping task '{task.name or '?'}' - missing required parameters")
            return

        scheduled = ScheduledTask(task, self._now())
        self.tasks[task.name] = scheduled
        jitter_note = f" (jitter 0–{task.jitter}s)" if task.jitter else ""
        log.info(f"Added scheduled task '{task.name}' to run every {task.interval} {task.unit.value}{jitter_note}")

    def remove_task(self, name: str) -> bool:
        """Remove a scheduled task."""
        if name in self.tasks:
            del self.tasks[name]
            log.info(f"Removed scheduled task '{name}'")
            return True
        return False

    def get_task(self, name: str) -> Optional[ScheduledTask]:
        """Get a scheduled task by name."""
        return self.tasks.get(name)

    def list_tasks(self) -> list[str]:
        """List all scheduled task names."""
        return list(self.tasks.keys())

    async def _run_task(self, scheduled: ScheduledTask) -> None:
        """Run a single task."""
        scheduled.running = True
        try:
            log.debug(f"Running scheduled task '{scheduled.name}'")
            await scheduled.task.run()

            scheduled.last_run = self._now()
            scheduled.calculate_next_run()
            if scheduled.next_run:
                log.debug(f"Completed scheduled task '{scheduled.name}', next run at {scheduled.next_run.strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                log.debug(f"Completed scheduled task '{scheduled.name}'")

        except Exception as e:
            log.error(f"Error running scheduled task '{scheduled.name}': {e}")
            # Don't update last_run on error, so it will retry next cycle
        finally:
            scheduled.running = False

    async def _scheduler_loop(self) -> None:
        """Main scheduler loop that checks for tasks to run."""
        log.info("Starting cron scheduler...")

        while self.running:
            now = self._now()
            tasks_to_run = []

            # Check which tasks need to run
            for scheduled in self.tasks.values():
                if scheduled.is_due(now):
                    scheduled.running = True
                    tasks_to_run.append(scheduled)

            # Run tasks that are due
            if tasks_to_run:
                log.debug(f"Running {len(tasks_to_run)} scheduled tasks")
                for scheduled in tasks_to_run:
                    asyncio.create_task(self._run_task(scheduled))

            # Wait before next check
            await asyncio.sleep(self.check_interval)

        log.info("Cron scheduler stopped")

    async def start(self) -> None:
        """Start the scheduler."""
        if not self.running:
            self.running = True
            asyncio.create_task(self._scheduler_loop())

    async def stop(self) -> None:
        """Stop the scheduler."""
        self.running = False
