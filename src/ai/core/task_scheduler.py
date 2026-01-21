# -*- coding: utf-8 -*-
"""Priority-based task scheduler with simple concurrency slots."""

from typing import Dict, List, Optional
from .models import TaskAssignment


class TaskScheduler:
    """A lightweight scheduler that keeps priority ordering and basic concurrency control."""

    def __init__(self, max_concurrent: int = 1, per_type_limits: Optional[Dict[str, int]] = None):
        self.max_concurrent = max_concurrent
        self.per_type_limits = per_type_limits or {}
        self.queue: List[TaskAssignment] = []
        self.active_count = 0
        self.active_by_type: Dict[str, int] = {}
        self._order_counter = 0  # stable ordering within same priority

    def add_tasks(self, tasks: List[TaskAssignment]):
        """Push tasks into the queue and keep it ordered by priority then FIFO."""
        for task in tasks:
            # Attach an internal order to preserve insertion sequence among same priority
            setattr(task, "_order", self._order_counter)
            self._order_counter += 1
            self.queue.append(task)
        self.queue.sort(key=lambda t: (t.priority, getattr(t, "_order", 0)))

    def next_task(self) -> Optional[TaskAssignment]:
        """Pop next runnable task considering concurrency slots."""
        if not self.queue:
            return None

        if self.active_count >= self.max_concurrent:
            return None

        # find first task whose type has free slot
        for idx, task in enumerate(self.queue):
            active_for_type = self.active_by_type.get(task.agent_type, 0)
            type_limit = self.per_type_limits.get(task.agent_type, self.max_concurrent)
            if active_for_type < type_limit:
                self.active_by_type[task.agent_type] = active_for_type + 1
                self.active_count += 1
                return self.queue.pop(idx)
        return None

    def mark_complete(self, task: TaskAssignment):
        """Release the slot for a finished task."""
        self.active_count = max(0, self.active_count - 1)
        if task and task.agent_type in self.active_by_type:
            self.active_by_type[task.agent_type] = max(0, self.active_by_type[task.agent_type] - 1)

    def has_pending(self) -> bool:
        return bool(self.queue)

    def reset(self):
        self.queue.clear()
        self.active_count = 0
        self.active_by_type.clear()
