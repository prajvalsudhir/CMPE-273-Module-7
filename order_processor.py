"""Versioned order processing.

An order moves through versioned states, e.g. CREATED (v1) -> PAID (v2)
-> SHIPPED (v3). Events may arrive late, out of order, or more than
once. Ordering is decided by the version number, not by arrival time
or by a timestamp.

Every update is an OrderEvent carrying order_id, version, and status
(plus, for worker updates, the worker name and its fencing token).

Rules:
- An event is applied only when its version is the next expected one.
- A later version arriving early is buffered as pending; the order
  does not jump ahead, and the missing version is recorded.
- A version already applied, or already pending, is a duplicate and
  is ignored. A pending version arriving again with a different
  status is a conflict: it is rejected and the original is kept.
- A worker update must carry a fencing token. A token older than the
  highest token seen for the order is stale and is rejected, and a
  worker update with no token at all is rejected too.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class OrderEvent:
    order_id: str
    version: int
    status: str
    worker: str | None = None
    fencing_token: int | None = None


class Order:
    def __init__(self, order_id):
        self.order_id = order_id
        self.status = None
        self.next_version = 1
        self.applied = set()
        self.pending = {}  # version -> status
        self.fencing_token = 0

    def missing_versions(self):
        if not self.pending:
            return []
        return [v for v in range(self.next_version, max(self.pending) + 1)
                if v not in self.pending]

    def receive(self, event):
        """Receive one event. Returns True if it changed the order."""
        version, status = event.version, event.status
        if event.worker:
            token = (f"token {event.fencing_token}"
                     if event.fencing_token is not None else "no token")
            print(f"[RECEIVED] {event.order_id} v{version} {status} "
                  f"from {event.worker} ({token})")
        else:
            print(f"[RECEIVED] {event.order_id} v{version} {status}")

        if event.order_id != self.order_id:
            print(f"[REJECTED] {self.order_id} v{version} {status}: "
                  f"event is for {event.order_id}, not {self.order_id}")
            return False

        if event.worker is not None and event.fencing_token is None:
            print(f"[REJECTED] {self.order_id} v{version} {status} "
                  f"from {event.worker}: worker update requires a "
                  f"fencing token")
            return False

        if event.fencing_token is not None:
            if event.fencing_token < self.fencing_token:
                print(f"[REJECTED] {self.order_id} v{version} {status} "
                      f"from {event.worker}: stale fencing token "
                      f"{event.fencing_token} < current "
                      f"{self.fencing_token}")
                return False
            self.fencing_token = event.fencing_token

        if version in self.applied or version < self.next_version:
            print(f"[IGNORED]  {self.order_id} v{version} {status}: "
                  f"duplicate, already applied")
            return False

        if version in self.pending:
            if self.pending[version] == status:
                print(f"[IGNORED]  {self.order_id} v{version} {status}: "
                      f"duplicate, already pending")
            else:
                print(f"[REJECTED] {self.order_id} v{version} {status}: "
                      f"conflicts with pending v{version} "
                      f"{self.pending[version]}; original kept")
            return False

        if version > self.next_version:
            self.pending[version] = status
            missing = list(range(self.next_version, version))
            print(f"[BUFFERED] {self.order_id} v{version} {status}: "
                  f"waiting for missing version(s) {missing}; "
                  f"status stays {self.status}")
            return False

        self._apply(version, status)
        while self.next_version in self.pending:
            v = self.next_version
            self._apply(v, self.pending.pop(v))
        return True

    def _apply(self, version, status):
        self.status = status
        self.applied.add(version)
        self.next_version = version + 1
        print(f"[APPLIED]  {self.order_id} v{version} {status} "
              f"-> status is now {self.status}")

    def summary(self):
        pending = sorted(self.pending)
        return (f"{self.order_id}: status={self.status}, "
                f"next expected version={self.next_version}, "
                f"pending versions={pending if pending else 'none'}")
