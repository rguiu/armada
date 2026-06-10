"""Tests for armada_ai.metrics."""
import pytest
from armada_ai import metrics


@pytest.fixture(autouse=True)
def reset_metrics():
    with metrics._lock:
        metrics._registry.clear()
    yield


class TestRegister:
    def test_register_counter(self):
        metrics.register_counter("test_counter", "A test counter")
        assert "test_counter" in metrics._registry
        assert metrics._registry["test_counter"]["type"] == "counter"

    def test_register_gauge(self):
        metrics.register_gauge("test_gauge", "A test gauge")
        assert "test_gauge" in metrics._registry
        assert metrics._registry["test_gauge"]["type"] == "gauge"

    def test_register_histogram(self):
        metrics.register_histogram("test_hist", "A test histogram")
        assert "test_hist" in metrics._registry
        assert metrics._registry["test_hist"]["type"] == "histogram"

    def test_register_with_labels(self):
        metrics.register_counter("test_labeled", "Labeled counter", ("method",))
        assert metrics._registry["test_labeled"]["labels"] == ("method",)


class TestCounter:
    def test_inc_default(self):
        metrics.register_counter("cnt", "Help")
        metrics.counter_inc("cnt")
        key = metrics._label_key(())
        assert metrics._registry["cnt"]["values"][key] == 1.0

    def test_inc_custom_value(self):
        metrics.register_counter("cnt", "Help")
        metrics.counter_inc("cnt", 5.0)
        key = metrics._label_key(())
        assert metrics._registry["cnt"]["values"][key] == 5.0

    def test_inc_accumulates(self):
        metrics.register_counter("cnt", "Help")
        metrics.counter_inc("cnt", 3.0)
        metrics.counter_inc("cnt", 4.0)
        key = metrics._label_key(())
        assert metrics._registry["cnt"]["values"][key] == 7.0

    def test_inc_with_labels(self):
        metrics.register_counter("cnt", "Help", ("method",))
        metrics.counter_inc("cnt", 2.0, ("GET",))
        key = metrics._label_key(("GET",))
        assert metrics._registry["cnt"]["values"][key] == 2.0

    def test_inc_unregistered_is_noop(self):
        metrics.counter_inc("nonexistent")

    def test_inc_multiple_label_pairs(self):
        metrics.register_counter("cnt", "Help", ("method",))
        metrics.counter_inc("cnt", 1.0, ("GET",))
        metrics.counter_inc("cnt", 2.0, ("POST",))
        assert metrics._registry["cnt"]["values"][metrics._label_key(("GET",))] == 1.0
        assert metrics._registry["cnt"]["values"][metrics._label_key(("POST",))] == 2.0


class TestGauge:
    def test_set_value(self):
        metrics.register_gauge("g", "Help")
        metrics.gauge_set("g", 42.0)
        key = metrics._label_key(())
        assert metrics._registry["g"]["values"][key] == 42.0

    def test_set_overwrites(self):
        metrics.register_gauge("g", "Help")
        metrics.gauge_set("g", 10.0)
        metrics.gauge_set("g", 20.0)
        assert metrics._registry["g"]["values"][metrics._label_key(())] == 20.0

    def test_set_with_labels(self):
        metrics.register_gauge("g", "Help", ("status",))
        metrics.gauge_set("g", 3.0, ("active",))
        assert metrics._registry["g"]["values"][metrics._label_key(("active",))] == 3.0

    def test_set_unregistered_is_noop(self):
        metrics.gauge_set("nonexistent", 1.0)


class TestHistogram:
    def test_observe_single(self):
        metrics.register_histogram("h", "Help")
        metrics.histogram_observe("h", 2.5)
        key = metrics._label_key(())
        v = metrics._registry["h"]["values"][key]
        assert v["sum"] == 2.5
        assert v["count"] == 1
        for b in metrics.HISTOGRAM_BUCKETS:
            if b >= 2.5:
                assert v["buckets"][b] == 1
            else:
                assert v["buckets"][b] == 0

    def test_observe_multiple(self):
        metrics.register_histogram("h", "Help")
        metrics.histogram_observe("h", 0.05)
        metrics.histogram_observe("h", 100.0)
        key = metrics._label_key(())
        v = metrics._registry["h"]["values"][key]
        assert v["sum"] == 100.05
        assert v["count"] == 2

    def test_observe_with_labels(self):
        metrics.register_histogram("h", "Help", ("endpoint",))
        metrics.histogram_observe("h", 1.0, ("/api",))
        key = metrics._label_key(("/api",))
        assert metrics._registry["h"]["values"][key]["count"] == 1


class TestGenerateLatest:
    def test_empty_registry(self):
        result = metrics.generate_latest()
        assert result.endswith("\n")

    def test_counter_output(self):
        metrics.register_counter("requests_total", "Total requests")
        metrics.counter_inc("requests_total", 10.0)
        output = metrics.generate_latest()
        assert "# HELP requests_total Total requests" in output
        assert "# TYPE requests_total counter" in output
        assert "requests_total 10 " in output

    def test_gauge_output(self):
        metrics.register_gauge("temperature", "Current temp")
        metrics.gauge_set("temperature", 98.6)
        output = metrics.generate_latest()
        assert "# HELP temperature Current temp" in output
        assert "# TYPE temperature gauge" in output
        assert "temperature 98.6" in output

    def test_histogram_output(self):
        metrics.register_histogram("latency", "Request latency")
        metrics.histogram_observe("latency", 2.0)
        output = metrics.generate_latest()
        assert "# HELP latency Request latency" in output
        assert "# TYPE latency histogram" in output
        assert "latency_sum 2 " in output
        assert "latency_count 1 " in output
        assert "latency_bucket" in output
        assert 'le="+Inf"' in output

    def test_labeled_output(self):
        metrics.register_counter("requests_total", "Total", ("method",))
        metrics.counter_inc("requests_total", 5.0, ("GET",))
        output = metrics.generate_latest()
        assert 'method="GET"' in output
        assert "requests_total" in output

    def test_format_no_decimal(self):
        metrics.register_gauge("int_gauge", "Help")
        metrics.gauge_set("int_gauge", 4.0)
        output = metrics.generate_latest()
        assert "int_gauge 4 " in output

    def test_format_small_decimal(self):
        metrics.register_gauge("small_gauge", "Help")
        metrics.gauge_set("small_gauge", 0.00012345)
        output = metrics.generate_latest()
        assert "small_gauge" in output
        assert "e-" in output or "0.00012" in output


class TestInit:
    def test_registers_default_metrics(self):
        metrics.init()
        assert "armada_uptime_seconds" in metrics._registry
        assert "armada_agents" in metrics._registry
        assert "armada_reports_total" in metrics._registry
        assert "armada_errors_total" in metrics._registry
        assert "armada_nodes_created_total" in metrics._registry
        assert "armada_tokens_total" in metrics._registry
        assert "armada_cost_total" in metrics._registry
        assert "armada_report_latency_seconds" in metrics._registry


class TestFormatLe:
    def test_int_le(self):
        assert metrics._format_le(1.0) == "1"

    def test_float_le(self):
        assert metrics._format_le(0.1) == "0.1"
