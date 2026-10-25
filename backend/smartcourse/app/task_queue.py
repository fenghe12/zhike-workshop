"""Persistent course messages with a bounded pool of pipeline workers."""
import os
import socket
import threading

from .resource_scheduler import ResourceScheduler
from .task_model import utc_now


class TaskAlreadyQueued(ValueError):
    pass


class PersistentTaskQueue:
    def __init__(self, store, execute, workers=3):
        self.store = store
        self.execute = execute
        self.workers = max(1, min(5, int(workers)))
        self.resources = ResourceScheduler(store.path.parent)
        self._condition = threading.Condition(threading.RLock())
        self._threads = set()
        self._closed = False

    def submit(self, task_id, start_stage):
        def enqueue(data):
            messages = data.setdefault("executionQueue", [])
            if any(message["taskId"] == task_id for message in messages):
                raise TaskAlreadyQueued("任务已在队列中")
            task = data["tasks"][task_id]
            if task.get("status") == "processing" and task.get("queue", {}).get("state") in {"running", "waiting_resource"}:
                raise TaskAlreadyQueued("任务正在执行")
            now = utc_now()
            messages.append({"taskId": task_id, "startStage": start_stage, "enqueuedAt": now})
            task.update(status="queued", currentStage=start_stage, updatedAt=now,
                        queue={"state": "queued", "enqueuedAt": now})
            for field in ("workerPid", "workerHost", "error", "requiredAsset"):
                task.pop(field, None)
            task["stages"][start_stage - 1].update(status="queued", progress=0,
                                                  detail={"step": "等待课程工作进程"})
            for field in ("startedAt", "startedAtEpoch", "completedAt", "elapsedSeconds", "etaSeconds"):
                task["stages"][start_stage - 1].pop(field, None)
        with self._condition:
            if self._closed:
                raise RuntimeError("课程队列已关闭")
            self.store.transact(enqueue)
            self.start()

    def start(self):
        with self._condition:
            if self._closed:
                return
            pending = len(self.store.snapshot().get("executionQueue", []))
            for _ in range(min(pending, self.workers - len(self._threads))):
                worker = threading.Thread(target=self._work, name="smartcourse-queue", daemon=True)
                self._threads.add(worker)
                worker.start()

    def _claim(self, data):
        messages = data.setdefault("executionQueue", [])
        while messages:
            message = messages.pop(0)
            task = data["tasks"].get(message["taskId"])
            if task is None or task.get("status") != "queued":
                continue
            task.update(status="processing", workerPid=os.getpid(), workerHost=socket.gethostname(),
                        queue={**task.get("queue", {}), "state": "running"})
            return message
        return None

    def _work(self):
        try:
            while not self._closed:
                with self.resources.acquire("courses", self.workers):
                    if self._closed:
                        return
                    message = self.store.transact(self._claim)
                    if message is None:
                        return
                    task_id = message["taskId"]
                    try:
                        self.execute(task_id, message["startStage"])
                    finally:
                        def finish(data):
                            task = data["tasks"].get(task_id)
                            if task is not None and task.get("status") != "queued":
                                task["queue"] = {"state": task.get("status"), "finishedAt": utc_now()}
                        self.store.transact(finish)
                        with self._condition:
                            self._condition.notify_all()
        finally:
            with self._condition:
                self._threads.discard(threading.current_thread())
                self._condition.notify_all()
                self.start()

    def wait(self, task_id):
        with self._condition:
            while True:
                task = self.store.snapshot()["tasks"].get(task_id)
                if task is None or task.get("status") not in {"queued", "processing", "running"}:
                    return
                self._condition.wait(timeout=0.2)

    def close(self, wait=True):
        with self._condition:
            self._closed = True
            threads = list(self._threads)
            self._condition.notify_all()
        if wait:
            for worker in threads:
                worker.join()


def with_queue_position(task, data):
    if task.get("queue", {}).get("state") == "queued":
        pending = [message["taskId"] for message in data.get("executionQueue", [])]
        if task["id"] in pending:
            task["queue"]["position"] = pending.index(task["id"]) + 1
    return task
