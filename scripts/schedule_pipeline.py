"""Lab 5 Task 3: schedule the retraining pipeline.

    # prove a scheduled run fires (fires 3 minutes from now, every 15 minutes):
    python scripts/schedule_pipeline.py --test
    # after one scheduled run is observed:
    python scripts/schedule_pipeline.py --disable itcs355-lab5-test
    # the real trigger (weekly, Sunday 02:00 Japan time), created DISABLED to avoid surprise spend:
    python scripts/schedule_pipeline.py --weekly
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import config  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--test", action="store_true")
    g.add_argument("--weekly", action="store_true")
    g.add_argument("--disable")
    g.add_argument("--list", action="store_true")
    args = ap.parse_args()

    from cloudlayer import azure_ops, pipelines

    client = azure_ops.ml_client()
    if args.list:
        from azure.ai.ml.operations._schedule_operations import ScheduleListViewType

        for s in client.schedules.list(list_view_type=ScheduleListViewType.ALL):
            print(f"{s.name:<32} enabled={s.is_enabled}  trigger={type(s.trigger).__name__}")
        return 0
    if args.disable:
        client.schedules.begin_disable(args.disable).result()
        print(f"disabled {args.disable}")
        return 0

    from azure.ai.ml.constants import TimeZone
    from azure.ai.ml.entities import CronTrigger, JobSchedule, RecurrenceTrigger

    job = pipelines.compile_azure()
    tags = config.load(strict=False).tags(5)
    if args.test:
        start = (datetime.now(timezone.utc) + timedelta(minutes=3)).replace(tzinfo=None, microsecond=0)
        trigger = RecurrenceTrigger(frequency="minute", interval=15, start_time=start,
                                    time_zone=TimeZone.UTC)
        name = "itcs355-lab5-test"
    else:
        trigger = CronTrigger(expression="0 2 * * 0", time_zone=TimeZone.TOKYO_STANDARD_TIME)
        name = "itcs355-lab5-weekly"
    schedule = JobSchedule(name=name, trigger=trigger, create_job=job, tags=tags)
    created = client.schedules.begin_create_or_update(schedule).result()
    print(f"created schedule {created.name} enabled={created.is_enabled}")
    if args.weekly:
        client.schedules.begin_disable(name).result()
        print(f"{name} disabled after creation (definition kept as evidence; deleted at teardown)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
