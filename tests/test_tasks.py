import asyncio

from datetime import datetime, time, timezone
from unittest.mock import patch

import pytest

from future.interfaces.ITask import ITask
from future.lifespan import Lifespan
from future.scheduling import Unit, Weekday, WorkingHours
from future.taskscheduler import CronScheduler


class FlagTask(ITask):
    name = "flag"
    interval = 1
    unit = Unit.SECONDS
    ran = False

    async def run(self) -> None:
        FlagTask.ran = True


class CountTask(ITask):
    name = "count"
    interval = 1
    unit = Unit.SECONDS
    count = 0

    async def run(self) -> None:
        CountTask.count += 1


async def test_lifespan_runs_startup_and_shutdown_tasks():
    FlagTask.ran = False
    startup = FlagTask()
    shutdown = CountTask()
    CountTask.count = 0
    lifespan = Lifespan(startup_tasks=[startup], shutdown_tasks=[shutdown])
    await lifespan.__aenter__()
    assert FlagTask.ran is True
    assert CountTask.count == 0
    await lifespan.__aexit__(None, None, None)
    assert CountTask.count == 1


def test_scheduler_skips_incomplete_tasks():
    scheduler = CronScheduler()

    class Incomplete(ITask):
        name = "incomplete"
        interval = None
        unit = None

        async def run(self) -> None:
            pass

    scheduler.add_task(Incomplete())
    assert scheduler.list_tasks() == []


def test_scheduler_add_list_remove():
    scheduler = CronScheduler()
    scheduler.add_task(CountTask())
    assert scheduler.list_tasks() == ["count"]
    assert scheduler.get_task("count") is not None
    assert scheduler.remove_task("count") is True
    assert scheduler.list_tasks() == []
    assert scheduler.remove_task("count") is False


async def test_scheduler_run_task_invokes_run():
    CountTask.count = 0
    scheduler = CronScheduler()
    scheduler.add_task(CountTask())
    await scheduler._run_task(scheduler.get_task("count"))
    assert CountTask.count == 1
    assert scheduler.get_task("count").last_run is not None


async def test_scheduler_does_not_start_a_task_while_it_is_running():
    started = asyncio.Event()
    release = asyncio.Event()

    class SlowTask(ITask):
        name = "slow"
        interval = 1
        unit = Unit.HOURS

        def __init__(self) -> None:
            self.runs = 0

        async def run(self) -> None:
            self.runs += 1
            started.set()
            await release.wait()

    task = SlowTask()
    scheduler = CronScheduler()
    scheduler.check_interval = 0.01
    scheduler.add_task(task)
    await scheduler.start()
    await asyncio.wait_for(started.wait(), timeout=1)
    await asyncio.sleep(0.05)
    assert task.runs == 1
    release.set()
    await asyncio.sleep(0.02)
    await scheduler.stop()


def test_working_hours_allow_weekdays_with_end_exclusive():
    hours = WorkingHours(start=time(9), end=time(17), timezone="Europe/Oslo")

    assert hours.allows(datetime(2026, 1, 5, 8, 0, tzinfo=timezone.utc)) is True
    assert hours.allows(datetime(2026, 1, 5, 15, 59, tzinfo=timezone.utc)) is True
    assert hours.allows(datetime(2026, 1, 5, 16, 0, tzinfo=timezone.utc)) is False
    assert hours.allows(datetime(2026, 1, 10, 10, 0, tzinfo=timezone.utc)) is False


def test_overnight_working_hours_belong_to_the_opening_day():
    hours = WorkingHours(start=time(22), end=time(6), timezone="UTC", weekdays=frozenset({Weekday.FRIDAY}))

    assert hours.allows(datetime(2026, 1, 9, 23, 0, tzinfo=timezone.utc)) is True
    assert hours.allows(datetime(2026, 1, 10, 5, 59, tzinfo=timezone.utc)) is True
    assert hours.allows(datetime(2026, 1, 10, 6, 0, tzinfo=timezone.utc)) is False
    assert hours.allows(datetime(2026, 1, 10, 23, 0, tzinfo=timezone.utc)) is False


def test_working_hours_handle_both_sides_of_a_dst_fold():
    hours = WorkingHours(start=time(2), end=time(3), timezone="Europe/Oslo", weekdays=frozenset({Weekday.SUNDAY}))

    assert hours.allows(datetime(2026, 10, 25, 0, 30, tzinfo=timezone.utc)) is True
    assert hours.allows(datetime(2026, 10, 25, 1, 30, tzinfo=timezone.utc)) is True


def test_working_hours_validate_configuration():
    with pytest.raises(ValueError, match="different"):
        WorkingHours(start=time(9), end=time(9))
    with pytest.raises(ValueError, match="cannot be empty"):
        WorkingHours(start=time(9), end=time(17), weekdays=frozenset())
    with pytest.raises(ValueError, match="timezone-aware"):
        WorkingHours(start=time(9), end=time(17)).allows(datetime(2026, 1, 5, 10))
    with pytest.raises(ValueError, match="Unknown"):
        WorkingHours(start=time(9), end=time(17), timezone="Not/A_Zone")


async def test_scheduler_defers_a_due_task_until_working_hours_without_catch_up():
    current_time = datetime(2026, 1, 5, 7, 0, tzinfo=timezone.utc)
    started = asyncio.Event()

    class WorkingHoursTask(ITask):
        name = "working-hours"
        interval = 15
        unit = Unit.MINUTES
        working_hours = WorkingHours(start=time(9), end=time(17), timezone="Europe/Oslo")

        def __init__(self) -> None:
            self.runs = 0

        async def run(self) -> None:
            self.runs += 1
            started.set()

    task = WorkingHoursTask()
    scheduler = CronScheduler(clock=lambda: current_time)
    scheduler.check_interval = 0.01
    scheduler.add_task(task)
    scheduled = scheduler.get_task(task.name)

    assert scheduled is not None
    await scheduler.start()
    try:
        await asyncio.sleep(0.03)
        assert task.runs == 0

        current_time = datetime(2026, 1, 5, 8, 0, tzinfo=timezone.utc)
        await asyncio.wait_for(started.wait(), timeout=1)
        await asyncio.sleep(0.03)
    finally:
        await scheduler.stop()

    assert task.runs == 1
    assert scheduled.next_run == datetime(2026, 1, 5, 8, 15, tzinfo=timezone.utc)


def test_jitter_that_crosses_closing_time_is_deferred():
    now = datetime(2026, 1, 5, 15, 59, 30, tzinfo=timezone.utc)

    class JitteredTask(ITask):
        name = "jittered"
        interval = 1
        unit = Unit.MINUTES
        jitter = 60
        working_hours = WorkingHours(start=time(9), end=time(17), timezone="Europe/Oslo")

        async def run(self) -> None:
            pass

    with patch("future.taskscheduler.random.uniform", return_value=45):
        scheduler = CronScheduler(clock=lambda: now)
        scheduler.add_task(JitteredTask())

    scheduled = scheduler.get_task("jittered")
    assert scheduled is not None
    assert scheduled.next_run == datetime(2026, 1, 5, 16, 0, 15, tzinfo=timezone.utc)
    assert scheduled.is_due(datetime(2026, 1, 5, 16, 0, 15, tzinfo=timezone.utc)) is False
    assert scheduled.is_due(datetime(2026, 1, 6, 8, 0, tzinfo=timezone.utc)) is True
