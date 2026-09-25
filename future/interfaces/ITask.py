from datetime import datetime
from typing import Optional

from future.interfacing import Interface
from future.scheduling import Unit, WorkingHours


class ITask(Interface):
    name: str = ""
    interval: Optional[int] = None
    unit: Optional[Unit] = None
    start_time: Optional[datetime] = None
    jitter: Optional[float] = None
    working_hours: Optional[WorkingHours] = None

    async def run(self) -> None:
        raise NotImplementedError
