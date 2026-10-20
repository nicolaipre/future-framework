# Lifespan
`future.lifespan.Lifespan` is the ASGI lifespan hook used for application tasks. Future creates an empty lifespan by default; pass one when the application has tasks to run at startup, on a schedule, or at shutdown.

```python
from future.lifespan import Lifespan
from future.interfaces.ITask import ITask
from future.taskscheduler import Unit
from future.application import Future
from app.tasks.ScrapeTask import ScrapeTask


class BootTask(ITask):
    name = "boot"

    async def run(self) -> None:
        ...


lifespan = Lifespan(
    startup_tasks=[BootTask()],
    shutdown_tasks=[],
    cron_tasks=[ScrapeTask()],
)
app = Future(lifespan=lifespan, config=config)
```

## Slots
| List | When |
|------|------|
| `startup_tasks` | Once on ASGI startup, in order |
| `cron_tasks` | Registered with the interval scheduler after startup |
| `shutdown_tasks` | Once on ASGI shutdown, after the scheduler stops |

Empty lists are fine:

```python
Lifespan(startup_tasks=[], shutdown_tasks=[], cron_tasks=[])
```

## Lifecycle
1. Start framework components such as configured authentication providers.
2. Run `startup_tasks` (`await task.run()`).
3. Start `CronScheduler` and register `cron_tasks`.
4. App serves traffic; interval tasks fire in the background.
5. On shutdown: stop the scheduler, run `shutdown_tasks`, then stop framework components in reverse order.

How to build an `ITask` (name, interval, jitter, …): see [Tasks](tasks.md).
