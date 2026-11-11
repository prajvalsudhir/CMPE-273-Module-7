"""Versioned order processing.

An order moves through versioned states, e.g. CREATED (v1) -> PAID (v2)
-> SHIPPED (v3). Events may arrive late, out of order, or more than
once. Ordering is decided by the version number, not by arrival time
or by a timestamp.

Rules:
- An event is applied only when its version is the next expected one.
- A later version arriving early is buffered as pending; the order
  does not jump ahead, and the missing version is recorded.
- A version already applied is a duplicate and is ignored.
- A worker update carries a fencing token. A token older than the
  highest token seen for the order is stale and is rejected.
"""


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

    def receive(self, version, status, worker=None, fencing_token=None):
        """Receive one event. Returns True if it changed the order."""
        print(f"[RECEIVED] {self.order_id} v{version} {status}"
              + (f" from {worker} (token {fencing_token})" if worker else ""))

        if fencing_token is not None:
            if fencing_token < self.fencing_token:
                print(f"[REJECTED] {self.order_id} v{version} {status} "
                      f"from {worker}: stale fencing token "
                      f"{fencing_token} < current {self.fencing_token}")
                return False
            self.fencing_token = fencing_token

        if version in self.applied or version < self.next_version:
            print(f"[IGNORED]  {self.order_id} v{version} {status}: "
                  f"duplicate, already applied")
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
