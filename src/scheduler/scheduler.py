"""
Job scheduler for Victor Trading System.
Manages automated news analysis and trading jobs.
"""
import asyncio
from datetime import datetime
from typing import Callable, Dict, List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.utils.logger import get_logger

logger = get_logger(__name__)


class TradingScheduler:
    """
    Scheduler for trading operations.

    Manages scheduled jobs for:
    - Morning news analysis
    - Intraday analysis and trading
    - Daily report generation
    - Risk limit reset
    """

    def __init__(self, config: dict, timezone: str = "Asia/Seoul"):
        """
        Initialize trading scheduler.

        Args:
            config: Scheduler configuration dictionary
            timezone: Timezone for job scheduling
        """
        self.config = config
        self.timezone = timezone
        self._scheduler = AsyncIOScheduler(timezone=timezone)
        self._jobs: Dict[str, str] = {}  # job_name -> job_id
        self._handlers: Dict[str, Callable] = {}

    def register_handler(self, job_name: str, handler: Callable) -> None:
        """
        Register a handler for a job.

        Args:
            job_name: Name of the job
            handler: Async function to call
        """
        self._handlers[job_name] = handler
        logger.debug(f"Registered handler for job: {job_name}")

    def _parse_time(self, time_str: str) -> tuple:
        """Parse time string to (hour, minute)."""
        parts = time_str.split(":")
        return int(parts[0]), int(parts[1])

    def setup_jobs(self) -> None:
        """Setup all scheduled jobs from configuration."""
        jobs_config = self.config.get("jobs", {})

        # Morning analysis job
        if "morning_analysis" in jobs_config:
            time_str = jobs_config["morning_analysis"]
            hour, minute = self._parse_time(time_str)
            self._add_job(
                "morning_analysis",
                hour=hour,
                minute=minute,
                description="Morning news analysis",
            )

        # Intraday analysis jobs
        if "intraday_analysis" in jobs_config:
            times = jobs_config["intraday_analysis"].split(",")
            for i, time_str in enumerate(times):
                hour, minute = self._parse_time(time_str.strip())
                self._add_job(
                    f"intraday_analysis_{i}",
                    hour=hour,
                    minute=minute,
                    description=f"Intraday analysis at {time_str}",
                    handler_name="intraday_analysis",
                )

        # Daily report job
        if "daily_report" in jobs_config:
            time_str = jobs_config["daily_report"]
            hour, minute = self._parse_time(time_str)
            self._add_job(
                "daily_report",
                hour=hour,
                minute=minute,
                description="Daily analysis report",
            )

        # Risk reset job
        if "risk_reset" in jobs_config:
            time_str = jobs_config["risk_reset"]
            hour, minute = self._parse_time(time_str)
            self._add_job(
                "risk_reset",
                hour=hour,
                minute=minute,
                description="Daily risk limit reset",
            )

        logger.info(f"Scheduled {len(self._jobs)} jobs")

    def _add_job(
        self,
        job_name: str,
        hour: int,
        minute: int,
        description: str,
        handler_name: Optional[str] = None,
        day_of_week: str = "mon-fri",
    ) -> None:
        """
        Add a scheduled job.

        Args:
            job_name: Unique job identifier
            hour: Hour to run (0-23)
            minute: Minute to run (0-59)
            description: Job description
            handler_name: Handler to use (defaults to job_name)
            day_of_week: Days to run (default: weekdays)
        """
        handler_key = handler_name or job_name

        async def job_wrapper():
            """Wrapper to handle job execution."""
            logger.info(f"Starting job: {job_name} ({description})")
            try:
                handler = self._handlers.get(handler_key)
                if handler:
                    if asyncio.iscoroutinefunction(handler):
                        await handler()
                    else:
                        handler()
                    logger.info(f"Completed job: {job_name}")
                else:
                    logger.warning(f"No handler registered for: {handler_key}")
            except Exception as e:
                logger.error(f"Job {job_name} failed: {e}")

        trigger = CronTrigger(
            hour=hour,
            minute=minute,
            day_of_week=day_of_week,
            timezone=self.timezone,
        )

        job = self._scheduler.add_job(
            job_wrapper,
            trigger=trigger,
            id=job_name,
            name=description,
        )

        self._jobs[job_name] = job.id
        logger.debug(f"Added job: {job_name} at {hour:02d}:{minute:02d} ({day_of_week})")

    def start(self) -> None:
        """Start the scheduler."""
        if not self._scheduler.running:
            self._scheduler.start()
            logger.info("Scheduler started")

    def stop(self) -> None:
        """Stop the scheduler."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("Scheduler stopped")

    def pause_job(self, job_name: str) -> None:
        """Pause a specific job."""
        if job_name in self._jobs:
            self._scheduler.pause_job(self._jobs[job_name])
            logger.info(f"Paused job: {job_name}")

    def resume_job(self, job_name: str) -> None:
        """Resume a paused job."""
        if job_name in self._jobs:
            self._scheduler.resume_job(self._jobs[job_name])
            logger.info(f"Resumed job: {job_name}")

    def run_now(self, job_name: str) -> None:
        """Trigger a job to run immediately."""
        handler_key = job_name
        # Handle intraday_analysis variants
        if job_name.startswith("intraday_analysis"):
            handler_key = "intraday_analysis"

        handler = self._handlers.get(handler_key)
        if handler:
            logger.info(f"Running job immediately: {job_name}")
            if asyncio.iscoroutinefunction(handler):
                asyncio.create_task(handler())
            else:
                handler()
        else:
            logger.warning(f"No handler for job: {job_name}")

    def get_next_run_times(self) -> Dict[str, datetime]:
        """Get next run times for all jobs."""
        result = {}
        for job_name, job_id in self._jobs.items():
            job = self._scheduler.get_job(job_id)
            if job and job.next_run_time:
                result[job_name] = job.next_run_time
        return result

    def get_status(self) -> dict:
        """Get scheduler status."""
        return {
            "running": self._scheduler.running,
            "job_count": len(self._jobs),
            "jobs": list(self._jobs.keys()),
            "next_runs": {
                name: dt.isoformat() if dt else None
                for name, dt in self.get_next_run_times().items()
            },
        }
