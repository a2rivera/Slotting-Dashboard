import asyncio
import threading
import time
from collections import deque

from api_client import call_api
from app_helpers import normalize_cmdb_ci_display


_QUEUE = deque()  # entries: dict(sys_id, state)
_IN_FLIGHT: set[str] = set()
_LAST_ATTEMPT_TS: dict[str, float] = {}
_LOCK = threading.Lock()
_STARTED = False

# Tunables
COOLDOWN_SECONDS = 30 * 60          # don't re-poke the same task too frequently
MAX_BATCH_SIZE = 50                 # max tasks popped per loop
MAX_CONCURRENCY = 12                # parallel updates
STATE_HOLD_SECONDS = 1.5            # wait between state flips
IDLE_SLEEP_SECONDS = 2.0            # when queue is empty

PENDING_USER_INPUT = "Pending User Input"
WORK_IN_PROGRESS = "Work in Progress"


def _now() -> float:
    return time.time()


def _norm_state(value) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        # ServiceNow-style references sometimes come through as dicts
        return str(value.get("display_value") or value.get("value") or "").strip()
    return str(value).strip()


def start_ci_refresh_worker():
    """Idempotently start the daemon thread."""
    global _STARTED
    with _LOCK:
        if _STARTED:
            return
        _STARTED = True
    t = threading.Thread(target=lambda: asyncio.run(_run_loop()), daemon=True, name="ci-refresh-worker")
    t.start()


def enqueue_missing_ci_tasks(tickets: list[dict]):
    """
    Enqueue tasks with missing CI so we can "poke" CI population downstream by
    toggling the task state (non-blocking).
    """
    if not tickets:
        return

    start_ci_refresh_worker()

    with _LOCK:
        for item in tickets:
            sys_id = str(item.get("sys_id") or "").strip()
            if not sys_id:
                continue

            if normalize_cmdb_ci_display(item):
                continue

            state = _norm_state(item.get("state")).lower()
            if state in {"resolved", "closed", "cancelled"}:
                continue

            last = _LAST_ATTEMPT_TS.get(sys_id, 0.0)
            if (_now() - last) < COOLDOWN_SECONDS:
                continue

            if sys_id in _IN_FLIGHT:
                continue

            _QUEUE.append({"sys_id": sys_id, "state": _norm_state(item.get("state"))})


async def _fetch_task_by_sys_id(sys_id: str) -> dict | None:
    """Fetch latest task record so we don't update if CI is already populated."""
    spec = {
        "url": "http://configurationitem/table/task?SystemID=SOAP-UI&ReferenceID=*&MaxRows=1",
        "headers": {
            "accept": "application/json",
            "QueryParams": f"sysparm_query=sys_id={sys_id}",
        },
        "method": "GET",
    }
    resp = await call_api(spec["url"], headers=spec["headers"], method=spec["method"])
    if not resp or "result" not in resp:
        return None
    results = resp.get("result") or []
    if not results:
        return None
    return results[0]


async def _still_missing_ci(sys_id: str) -> bool:
    task = await _fetch_task_by_sys_id(sys_id)
    if not task:
        # If we can't confirm, be conservative and don't touch it.
        return False
    return normalize_cmdb_ci_display(task) == ""


async def _update_task_state(sys_id: str, new_state: str):
    spec = {
        "url": "http://ConfigurationItem/table/task?SystemID=SystemID&ReferenceID=ReferenceID",
        "params": {
            "TaskID": sys_id,
            "State": new_state,
            "WorkNotes": "Auto CI refresh: temporary state update to trigger CI population.",
        },
        "headers": {"accept": "application/json"},
        "method": "PUT",
    }
    return await call_api(spec["url"], params=spec["params"], headers=spec["headers"], method=spec["method"])


async def _poke_task_state(sys_id: str, current_state: str):
    """
    If already Pending User Input, flip to WIP then back.
    Otherwise, set to Pending User Input.
    """
    if not await _still_missing_ci(sys_id):
        return

    cur = (current_state or "").strip().lower()
    if cur == PENDING_USER_INPUT.lower():
        await _update_task_state(sys_id, WORK_IN_PROGRESS)
        await asyncio.sleep(STATE_HOLD_SECONDS)
        if not await _still_missing_ci(sys_id):
            return
        await _update_task_state(sys_id, PENDING_USER_INPUT)
    else:
        await _update_task_state(sys_id, PENDING_USER_INPUT)


async def _run_loop():
    while True:
        batch = []
        with _LOCK:
            while _QUEUE and len(batch) < MAX_BATCH_SIZE:
                entry = _QUEUE.popleft()
                sys_id = entry["sys_id"]
                _IN_FLIGHT.add(sys_id)
                _LAST_ATTEMPT_TS[sys_id] = _now()
                batch.append(entry)

        if not batch:
            await asyncio.sleep(IDLE_SLEEP_SECONDS)
            continue

        sem = asyncio.Semaphore(MAX_CONCURRENCY)

        async def run_one(entry: dict):
            sys_id = entry["sys_id"]
            try:
                async with sem:
                    await _poke_task_state(sys_id=sys_id, current_state=entry.get("state", ""))
            except Exception as e:
                print(f"CI refresh state poke failed for {sys_id}: {e}")
            finally:
                with _LOCK:
                    _IN_FLIGHT.discard(sys_id)

        await asyncio.gather(*(run_one(e) for e in batch))

