"""Demos for versioned order processing.

Usage:
    python3 main.py                  # run all three demos
    python3 main.py ordering         # out-of-order + duplicate delivery
    python3 main.py missing          # later version only, earlier missing
    python3 main.py fencing          # stale worker rejected by fencing token
"""

import sys

from order_processor import Order, OrderEvent


def demo_ordering():
    print("=== 1. Versioned event ordering ===")
    print("Delivery order: v2, v2 again, v2 with a different status, "
          "v1, v2 again")
    order = Order("order-123")
    order.receive(OrderEvent("order-123", 2, "PAID"))
    order.receive(OrderEvent("order-123", 2, "PAID"))
    order.receive(OrderEvent("order-123", 2, "SHIPPED"))
    order.receive(OrderEvent("order-123", 1, "CREATED"))
    order.receive(OrderEvent("order-123", 2, "PAID"))
    print(order.summary())
    print()


def demo_missing():
    print("=== 2. Missing event ===")
    print("Only v2 arrives; v1 is missing")
    order = Order("order-456")
    order.receive(OrderEvent("order-456", 2, "PAID"))
    print(order.summary())
    print()


def demo_fencing():
    print("=== 3. Stale worker ===")
    print("Worker A has token 1, worker B has token 2")
    order = Order("order-789")
    order.receive(OrderEvent("order-789", 1, "CREATED",
                             worker="worker-A", fencing_token=1))
    order.receive(OrderEvent("order-789", 2, "PAID",
                             worker="worker-B", fencing_token=2))
    order.receive(OrderEvent("order-789", 3, "SHIPPED",
                             worker="worker-A"))
    order.receive(OrderEvent("order-789", 3, "SHIPPED",
                             worker="worker-A", fencing_token=1))
    order.receive(OrderEvent("order-789", 3, "SHIPPED",
                             worker="worker-B", fencing_token=2))
    print(order.summary())
    print()


DEMOS = {"ordering": demo_ordering, "missing": demo_missing,
         "fencing": demo_fencing}


def main():
    if len(sys.argv) == 1:
        for demo in DEMOS.values():
            demo()
    elif sys.argv[1] in DEMOS:
        DEMOS[sys.argv[1]]()
    else:
        print(f"Unknown demo: {sys.argv[1]}. Choose from: "
              + ", ".join(DEMOS))
        sys.exit(1)


if __name__ == "__main__":
    main()
