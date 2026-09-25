# Tasks
`future.interfaces.ITask` is the base for scheduled work — extend it, implement `async def run`, and pass instances into `Lifespan` (startup, shutdown, or `cron_tasks`).

```python
from future.interfaces.ITask import ITask
from future.scheduling import Unit, Weekday, WorkingHours
```

## ITask fields
| Attribute | Role |
|-----------|------|
| `name` | Label in logs / scheduler |
| `interval` | How often (required for `cron_tasks`) |
| `unit` | `Unit.SECONDS` / `MINUTES` / `HOURS` / `DAYS` |
| `start_time` | First run time (`datetime`); default is “now” when registered |
| `jitter` | Optional extra delay `0 … jitter` seconds on each next-run calculation |
| `working_hours` | Optional `WorkingHours` constraint for interval tasks |

Cron tasks need `name`, `interval`, and `unit`. Startup / shutdown tasks only need `name` and `run` (interval is ignored).

## Define a task
```python
from future.interfaces.ITask import ITask
from future.scheduling import Unit


class ScrapeTask(ITask):
    name = "scrape"
    interval = 1
    unit = Unit.HOURS

    async def run(self) -> None:
        ...


class BootTask(ITask):
    name = "boot"

    async def run(self) -> None:
        ...
```

## Working hours

An interval task can be restricted to a local-time window. The default weekdays are Monday through Friday:

```python
from datetime import time

from future.interfaces.ITask import ITask
from future.scheduling import Unit, WorkingHours


class SyncCustomers(ITask):
    name = "sync-customers"
    interval = 15
    unit = Unit.MINUTES
    working_hours = WorkingHours(
        start=time(8),
        end=time(17),
        timezone="Europe/Oslo",
    )

    async def run(self) -> None:
        ...
```

Pass `weekdays` to customize the opening days:

```python
working_hours = WorkingHours(
    start=time(22),
    end=time(6),
    timezone="Europe/Oslo",
    weekdays=frozenset({Weekday.FRIDAY, Weekday.SATURDAY}),
)
```

The start is inclusive and the end is exclusive. Overnight windows belong to the day on which they open, so Friday `22:00–06:00` includes early Saturday morning. If an interval becomes due while the window is closed, it runs once when the next window opens; missed intervals are not replayed. Time-zone and daylight-saving transitions are handled with the standard-library zone database.

## Wire into Lifespan
```python
from datetime import datetime, timedelta
from future.application import Future
from future.lifespan import Lifespan
from app.tasks.ScrapeTask import ScrapeTask
from app.tasks.CleanupTask import CleanupTask
from future.tasks.CheckDNSTask import CheckDNSTask

startup_tasks = [
    BootTask(),
]

shutdown_tasks = [
    CleanupTask(),
]

cron_tasks = [
    ScrapeTask(),
    CheckDNSTask(domain="example.com"),
]

lifespan = Lifespan(
    startup_tasks=startup_tasks,
    shutdown_tasks=shutdown_tasks,
    cron_tasks=cron_tasks,
)
app = Future(lifespan=lifespan, config=config)
```

## Startup and shutdown
On ASGI lifespan enter, Future runs each `startup_tasks` entry in order (`await task.run()`), then starts the scheduler and registers `cron_tasks`.

On exit, the scheduler stops, then `shutdown_tasks` run the same way.

## Interval (cron) tasks
Fixed intervals with optional working-hour constraints — not crontab expressions. `future.taskscheduler.CronScheduler` checks about once per second and runs due tasks concurrently (`asyncio.create_task`). Errors are logged; `last_run` is not updated on failure so the task retries on the next eligible cycle.

Each uvicorn **worker** runs its own scheduler (no cross-worker lock).

## Generate a task stub
```bash
future make:task Cleanup
```

Creates `app/tasks/CleanupTask.py` extending `ITask` — add it to a Lifespan list:

```python
from app.tasks.CleanupTask import CleanupTask

cron_tasks = [CleanupTask()]
```

## Built-in examples
`future.tasks.CheckDNSTask`, `future.tasks.CheckHttpStatusTask`, `future.tasks.DailyBackupTask`, and similar modules provide small sample tasks. Prefer app-specific modules under `app/tasks/` for real work.

See [Lifespan](lifespan.md) for the ASGI wrapper that runs these lists.
