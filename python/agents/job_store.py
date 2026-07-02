"""Thread-safe in-memory store for long-running scrape jobs (poll delivery).

A multi-minute scrape cannot ride a single HTTP request: the Telegram-miniapp
WebView drops connections on suspend/screen-lock, and Render's edge proxy kills
byte-less responses at ~100s. So the scrape runs in a worker thread that appends
results here, and the UI polls a snapshot endpoint with a `since` cursor —
every poll is a sub-second request that survives suspends and reconnects.

Memory-bounded for the 512MB Render tier: capped results per job, capped job
count, TTL eviction of stale/finished jobs. All state is process-local — after
a restart every prior job_id is unknown (snapshot returns None → 404), which
the frontend surfaces as "server restarted, retry".
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from utils.logger import log_agent_action

MAX_RESULTS_PER_JOB = 500     # ~1-2KB per project dict → ≤1MB per job
MAX_JOBS = 8
STALE_ACTIVE_SECS = 1800.0    # active job with no updates — assume the worker died
RETENTION_DONE_SECS = 600.0   # keep finished jobs briefly for late pollers

_TERMINAL = ("done", "error", "cancelled")


@dataclass
class Job:
    id: str
    kind: str                 # "kwork" | "workzilla"
    fingerprint: str          # single-flight key (search params hash)
    status: str = "pending"   # pending | running | done | error | cancelled
    results: list[dict[str, Any]] = field(default_factory=list)
    progress: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    truncated: bool = False   # hit MAX_RESULTS_PER_JOB or a worker deadline — results incomplete
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    cancel: threading.Event = field(default_factory=threading.Event)
    seen_urls: set[str] = field(default_factory=set)


class JobStore:
    """All public methods are lock-guarded with sub-millisecond critical
    sections: the worker thread appends, the event loop snapshots — never hold
    the lock across anything slower than a list copy."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}
        self._active_by_fingerprint: dict[str, str] = {}

    def create(self, kind: str, fingerprint: str) -> tuple[Job, bool]:
        """Return (job, reused). Single-flight: an active job with the same
        fingerprint is returned instead of creating a duplicate — the global
        Kwork rate limiter serializes scrapes anyway, so a second identical
        request should just poll the scrape already in progress."""
        with self._lock:
            self._evict_locked()
            existing_id = self._active_by_fingerprint.get(fingerprint)
            if existing_id:
                existing = self._jobs.get(existing_id)
                if existing is not None and existing.status not in _TERMINAL:
                    return existing, True
            job = Job(id=uuid.uuid4().hex[:12], kind=kind, fingerprint=fingerprint)
            self._jobs[job.id] = job
            self._active_by_fingerprint[fingerprint] = job.id
            return job, False

    def append(self, job_id: str, item: dict[str, Any]) -> None:
        """Append one result item; dedupes by item["url"] when present (Workzilla
        `_update` events carry no url and are appended as-is). Silently drops
        when the job is gone (evicted), terminal, or at the result cap."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status in _TERMINAL:
                return
            if len(job.results) >= MAX_RESULTS_PER_JOB:
                job.truncated = True  # let the UI say "first N of possibly more"
                return
            url = item.get("url") if isinstance(item, dict) else None
            if url:
                if url in job.seen_urls:
                    return
                job.seen_urls.add(url)
            job.results.append(item)
            job.updated_at = time.time()

    def mark_truncated(self, job_id: str) -> None:
        """Flag that the job stopped early (worker deadline) — results are partial."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                job.truncated = True

    def set_progress(self, job_id: str, progress: dict[str, Any]) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status in _TERMINAL:
                return
            job.progress = dict(progress)
            job.updated_at = time.time()

    def set_status(self, job_id: str, status: str) -> None:
        with self._lock:
            self._set_status_locked(job_id, status)

    def set_error(self, job_id: str, error: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.error = error
            self._set_status_locked(job_id, "error")

    def cancel(self, job_id: str) -> bool:
        """Flag the job cancelled. The worker sees job.cancel and stops between
        pages/cards; the status flips immediately so the UI can stop polling
        without waiting for the worker to notice.

        Returns True only when an ACTIVE job was transitioned — a terminal or
        unknown job returns False, so callers never propagate the cancel to
        shared scraper state (e.g. the process-wide Workzilla cancel Event)
        because of a stale job_id."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status in _TERMINAL:
                return False
            job.cancel.set()
            self._set_status_locked(job_id, "cancelled")
            return True

    def snapshot(self, job_id: str, since: int = 0) -> Optional[dict[str, Any]]:
        """Copy of the job state with results[since:]. None = unknown job
        (evicted or the process restarted) — callers map that to 404."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            since = max(0, int(since))
            return {
                "status": job.status,
                "progress": dict(job.progress),
                "error": job.error,
                "truncated": job.truncated,
                "results": list(job.results[since:]),
                "next_since": len(job.results),
                "total": len(job.results),
            }

    def _set_status_locked(self, job_id: str, status: str) -> None:
        job = self._jobs.get(job_id)
        if job is None or job.status in _TERMINAL:
            # Terminal states are final: a worker finishing after an explicit
            # cancel must not flip cancelled → done.
            return
        job.status = status
        job.updated_at = time.time()
        if status in _TERMINAL:
            job.seen_urls = set()  # free the dedupe set; results stay for late polls
            if self._active_by_fingerprint.get(job.fingerprint) == job_id:
                del self._active_by_fingerprint[job.fingerprint]

    def _evict_locked(self) -> None:
        now = time.time()
        doomed = [
            jid for jid, job in self._jobs.items()
            if (now - job.updated_at) > (
                RETENTION_DONE_SECS if job.status in _TERMINAL else STALE_ACTIVE_SECS
            )
        ]
        for jid in doomed:
            self._remove_locked(jid)
        overflow = len(self._jobs) - (MAX_JOBS - 1)
        if overflow <= 0:
            return
        # Prefer evicting terminal jobs (LRU); if the cap is still exceeded,
        # evict the oldest ACTIVE jobs too — the hard cap must hold on 512MB.
        terminal_first = sorted(self._jobs.values(), key=lambda j: (j.status not in _TERMINAL, j.updated_at))
        for job in terminal_first[:overflow]:
            if job.status not in _TERMINAL:
                log_agent_action("JobStore", f"⚠️ evicting ACTIVE job {job.id} ({job.kind}) — job cap {MAX_JOBS} exceeded", level="WARNING")
            self._remove_locked(job.id)

    def _remove_locked(self, job_id: str) -> None:
        job = self._jobs.pop(job_id, None)
        if job is None:
            return
        if self._active_by_fingerprint.get(job.fingerprint) == job_id:
            del self._active_by_fingerprint[job.fingerprint]
        # A stale active job may still have a wedged worker: flag cancel so it
        # stops scraping; its appends become no-ops (job_id no longer resolves).
        job.cancel.set()


job_store = JobStore()
