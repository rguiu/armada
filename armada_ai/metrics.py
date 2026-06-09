import threading
import time

_registry: dict[str, dict] = {}
_lock = threading.Lock()

TYPE_COUNTER = "counter"
TYPE_GAUGE = "gauge"
TYPE_HISTOGRAM = "histogram"

HISTOGRAM_BUCKETS = (0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 300.0, 900.0, 3600.0)


def _ensure(name: str, mtype: str, help_text: str, labels: tuple[str, ...] = ()):
    with _lock:
        if name not in _registry:
            _registry[name] = {
                "type": mtype,
                "help": help_text,
                "labels": labels,
                "values": {},
            }


def _label_key(label_values: tuple[str, ...]) -> str:
    return "\0".join(label_values)


def _label_str(labels: tuple[str, ...], values: tuple[str, ...]) -> str:
    if not labels:
        return ""
    parts = [f'{k}="{v}"' for k, v in zip(labels, values)]
    return "{" + ",".join(parts) + "}"


def counter_inc(name: str, value: float = 1.0, labels: tuple[str, ...] = ()):
    with _lock:
        if name in _registry:
            key = _label_key(labels)
            entry = _registry[name]
            entry["values"][key] = entry["values"].get(key, 0.0) + value


def gauge_set(name: str, value: float, labels: tuple[str, ...] = ()):
    with _lock:
        if name in _registry:
            key = _label_key(labels)
            _registry[name]["values"][key] = value


def histogram_observe(name: str, value: float, labels: tuple[str, ...] = ()):
    with _lock:
        if name in _registry:
            key = _label_key(labels)
            entry = _registry[name]
            if key not in entry["values"]:
                entry["values"][key] = {"sum": 0.0, "count": 0, "buckets": {b: 0 for b in HISTOGRAM_BUCKETS}}
            v = entry["values"][key]
            v["sum"] += value
            v["count"] += 1
            for b in HISTOGRAM_BUCKETS:
                if value <= b:
                    v["buckets"][b] += 1


def register_counter(name: str, help_text: str, labels: tuple[str, ...] = ()):
    _ensure(name, TYPE_COUNTER, help_text, labels)


def register_gauge(name: str, help_text: str, labels: tuple[str, ...] = ()):
    _ensure(name, TYPE_GAUGE, help_text, labels)


def register_histogram(name: str, help_text: str, labels: tuple[str, ...] = ()):
    _ensure(name, TYPE_HISTOGRAM, help_text, labels)


def generate_latest() -> str:
    lines = []
    now_ms = int(time.time() * 1000)

    with _lock:
        for name, entry in sorted(_registry.items()):
            lines.append(f"# HELP {name} {entry['help']}")
            lines.append(f"# TYPE {name} {entry['type']}")

            for key, value in sorted(entry["values"].items()):
                label_vals = tuple(key.split("\0")) if key else ()
                labels_str = _label_str(entry["labels"], label_vals)

                if entry["type"] == TYPE_HISTOGRAM:
                    v = value
                    lines.append(f"{name}_sum{labels_str} {_format(v['sum'])} {now_ms}")
                    lines.append(f"{name}_count{labels_str} {v['count']} {now_ms}")
                    for b in HISTOGRAM_BUCKETS:
                        ble = _format_le(b)
                        lines.append(
                            f"{name}_bucket{_bucket_label(entry['labels'], label_vals, ble)} "
                            f"{v['buckets'][b]} {now_ms}"
                        )
                    lines.append(
                        f"{name}_bucket{_bucket_label(entry['labels'], label_vals, '+Inf')} "
                        f"{v['count']} {now_ms}"
                    )
                else:
                    lines.append(f"{name}{labels_str} {_format(value)} {now_ms}")

    return "\n".join(lines) + "\n"


def _format(v: float) -> str:
    if v == int(v):
        return str(int(v))
    return f"{v:.6g}"


def _format_le(b: float) -> str:
    if b == int(b):
        return str(int(b))
    return f"{b:.3g}"


def _bucket_label(labels: tuple[str, ...], values: tuple[str, ...], le: str) -> str:
    if not labels:
        return f'{{le="{le}"}}'
    parts = [f'{k}="{v}"' for k, v in zip(labels, values)]
    parts.append(f'le="{le}"')
    return "{" + ",".join(parts) + "}"


def init():
    register_gauge("armada_uptime_seconds", "Server uptime in seconds")
    register_gauge("armada_agents", "Number of agents", ("status",))
    register_counter("armada_reports_total", "Total agent status reports")
    register_counter("armada_errors_total", "Total error events")
    register_counter("armada_nodes_created_total", "Total nodes created")
    register_counter("armada_tokens_total", "Total tokens consumed", ("direction",))
    register_gauge("armada_cost_total", "Total cost in USD")
    register_histogram("armada_report_latency_seconds", "Latency of agent reports")
