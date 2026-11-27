"""Print job tracking and monitoring."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

log = logging.getLogger(__name__)


class JobState(Enum):
    """Print job states (matches IPP job-state values)."""
    PENDING = 3
    HELD = 4
    PROCESSING = 5
    STOPPED = 6
    CANCELED = 7
    ABORTED = 8
    COMPLETED = 9

    @classmethod
    def from_cups(cls, value: int) -> JobState:
        try:
            return cls(value)
        except ValueError:
            return cls.PENDING

    @property
    def display_name(self) -> str:
        return {
            JobState.PENDING: "Pending",
            JobState.HELD: "Held",
            JobState.PROCESSING: "Printing",
            JobState.STOPPED: "Stopped",
            JobState.CANCELED: "Canceled",
            JobState.ABORTED: "Failed",
            JobState.COMPLETED: "Completed",
        }.get(self, "Unknown")

    @property
    def is_finished(self) -> bool:
        return self in (JobState.CANCELED, JobState.ABORTED, JobState.COMPLETED)

    @property
    def is_success(self) -> bool:
        return self == JobState.COMPLETED


@dataclass
class PrintJobInfo:
    """Represents a print job in the queue."""
    job_id: int
    title: str = ""
    printer_name: str = ""
    state: JobState = JobState.PENDING
    filename: str = ""
    pages: int = 0
    created_at: float = 0.0
    error_message: str = ""

    @property
    def status_text(self) -> str:
        if self.error_message and self.state == JobState.ABORTED:
            return f"Failed: {self.error_message}"
        return self.state.display_name


class PrintJobManager:
    """Manages print job tracking.

    Can monitor active jobs via CUPS polling or internal tracking.
    """

    def __init__(self, backend) -> None:
        self._backend = backend
        self._tracked_jobs: dict[int, PrintJobInfo] = {}
        self._callbacks: list = []

    def submit_job(
        self,
        printer_name: str,
        filepath: str,
        title: str,
        options: dict[str, str],
        page_count: int = 0,
    ) -> PrintJobInfo:
        """Submit a print job and begin tracking it.

        Returns a PrintJobInfo for the submitted job.
        Raises CupsError on failure.
        """
        job_id = self._backend.print_file(printer_name, filepath, title, options)

        info = PrintJobInfo(
            job_id=job_id,
            title=title,
            printer_name=printer_name,
            state=JobState.PROCESSING,
            filename=filepath,
            pages=page_count,
            created_at=time.time(),
        )
        self._tracked_jobs[job_id] = info
        return info

    def get_tracked_jobs(self) -> list[PrintJobInfo]:
        """Return all tracked jobs, most recent first."""
        return sorted(
            self._tracked_jobs.values(),
            key=lambda j: j.created_at,
            reverse=True,
        )

    def refresh_job_status(self, job_id: int) -> Optional[PrintJobInfo]:
        """Refresh the status of a tracked job from CUPS."""
        if job_id not in self._tracked_jobs:
            return None

        attrs = self._backend.get_job_attributes(job_id)
        if not attrs:
            # Job may have completed and been purged from CUPS
            info = self._tracked_jobs[job_id]
            if not info.state.is_finished:
                info.state = JobState.COMPLETED
            return info

        info = self._tracked_jobs[job_id]
        info.state = JobState.from_cups(attrs.get("job-state", 3))

        reason = attrs.get("job-state-reasons", "")
        if isinstance(reason, (list, tuple)):
            reason = ", ".join(str(r) for r in reason)
        if info.state == JobState.ABORTED and reason:
            info.error_message = str(reason)

        return info

    def refresh_all(self) -> list[PrintJobInfo]:
        """Refresh status of all tracked jobs."""
        for job_id in list(self._tracked_jobs.keys()):
            self.refresh_job_status(job_id)
        return self.get_tracked_jobs()

    def cancel_job(self, job_id: int) -> bool:
        """Cancel a tracked job."""
        success = self._backend.cancel_job(job_id)
        if success and job_id in self._tracked_jobs:
            self._tracked_jobs[job_id].state = JobState.CANCELED
        return success

    def remove_completed(self) -> None:
        """Remove finished jobs from tracking."""
        self._tracked_jobs = {
            jid: info for jid, info in self._tracked_jobs.items()
            if not info.state.is_finished
        }

    def get_queue_from_cups(self) -> list[PrintJobInfo]:
        """Get the actual CUPS print queue (not just our tracked jobs)."""
        jobs_dict = self._backend.get_jobs(mine_only=False)
        result = []
        for job_id, attrs in jobs_dict.items():
            info = PrintJobInfo(
                job_id=int(job_id) if isinstance(job_id, str) else job_id,
                title=attrs.get("job-name", ""),
                printer_name=attrs.get("job-printer-uri", "").split("/")[-1],
                state=JobState.from_cups(attrs.get("job-state", 3)),
                created_at=attrs.get("time-at-creation", 0),
            )
            result.append(info)
        return sorted(result, key=lambda j: j.created_at, reverse=True)
