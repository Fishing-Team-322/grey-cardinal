from types import SimpleNamespace

from brain_api.infrastructure.scheduler.jobs import register_jobs


class FakeScheduler:
    def __init__(self) -> None:
        self.every_jobs = []
        self.daily_jobs = []

    def every(self, seconds, job, name):
        self.every_jobs.append((seconds, job, name))

    def daily_at(self, hour, job, name):
        self.daily_jobs.append((hour, job, name))


def test_yougile_discovery_is_scheduled_from_settings():
    scheduler = FakeScheduler()
    container = SimpleNamespace(
        settings=SimpleNamespace(yougile_discovery_schedule_hours=6),
        config=SimpleNamespace(morning_summary_hour=9, evening_digest_hour=20),
    )

    register_jobs(scheduler, container)

    assert (21600, "yougile_discovery") in [
        (seconds, name) for seconds, _job, name in scheduler.every_jobs
    ]
