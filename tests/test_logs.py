"""Tests for structured logging."""

import json
import os
import tempfile

from armada_ai import logs


def test_log_event_writes_file():
    logs.LOGS_DIR = tempfile.mkdtemp(prefix="_armada_test_logs_")
    try:
        logs.log_event("test-node", "create", {"agent_type": "bash"})
        log_path = os.path.join(logs.LOGS_DIR, "test-node.jsonl")
        assert os.path.exists(log_path)
        with open(log_path) as f:
            lines = f.readlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["type"] == "create"
        assert entry["name"] == "test-node"
        assert entry["data"]["agent_type"] == "bash"
    finally:
        import shutil
        shutil.rmtree(logs.LOGS_DIR, ignore_errors=True)


def test_get_node_logs():
    logs.LOGS_DIR = tempfile.mkdtemp(prefix="_armada_test_logs_")
    try:
        logs.log_event("alpha", "report", {"status": "active"})
        logs.log_event("alpha", "report", {"status": "idle"})
        logs.log_event("beta", "create", {})

        entries = logs.get_node_logs("alpha", limit=10)
        assert len(entries) == 2
        assert entries[0]["data"]["status"] == "idle"
        assert entries[1]["data"]["status"] == "active"

        entries = logs.get_node_logs("beta")
        assert len(entries) == 1
        assert entries[0]["type"] == "create"
    finally:
        import shutil
        shutil.rmtree(logs.LOGS_DIR, ignore_errors=True)


def test_get_node_logs_limit():
    logs.LOGS_DIR = tempfile.mkdtemp(prefix="_armada_test_logs_")
    try:
        for i in range(5):
            logs.log_event("limited", "report", {"i": i})
        entries = logs.get_node_logs("limited", limit=2)
        assert len(entries) == 2
    finally:
        import shutil
        shutil.rmtree(logs.LOGS_DIR, ignore_errors=True)


def test_get_node_logs_before_ts():
    logs.LOGS_DIR = tempfile.mkdtemp(prefix="_armada_test_logs_")
    try:
        import time
        logs.log_event("ts-test", "step1", {})
        time.sleep(0.1)
        cutoff = time.time()
        time.sleep(0.1)
        logs.log_event("ts-test", "step2", {})

        entries = logs.get_node_logs("ts-test", before_ts=cutoff)
        assert len(entries) == 1
        assert entries[0]["type"] == "step1"
    finally:
        import shutil
        shutil.rmtree(logs.LOGS_DIR, ignore_errors=True)


def test_get_node_logs_missing():
    logs.LOGS_DIR = tempfile.mkdtemp(prefix="_armada_test_logs_")
    try:
        entries = logs.get_node_logs("nonexistent")
        assert entries == []
    finally:
        import shutil
        shutil.rmtree(logs.LOGS_DIR, ignore_errors=True)


def test_search_logs():
    logs.LOGS_DIR = tempfile.mkdtemp(prefix="_armada_test_logs_")
    try:
        logs.log_event("searcher", "create", {"agent": "claude"})
        logs.log_event("searcher", "report", {"status": "active"})
        logs.log_event("other", "report", {"status": "idle"})

        results = logs.search_logs("claude", limit=10)
        assert len(results) == 1
        assert results[0]["type"] == "create"

        results = logs.search_logs("active", limit=10)
        assert len(results) == 1
    finally:
        import shutil
        shutil.rmtree(logs.LOGS_DIR, ignore_errors=True)


def test_search_logs_node_filter():
    logs.LOGS_DIR = tempfile.mkdtemp(prefix="_armada_test_logs_")
    try:
        logs.log_event("alpha", "report", {"status": "x"})
        logs.log_event("beta", "report", {"status": "x"})

        results = logs.search_logs("x", node_name="alpha")
        assert len(results) == 1
        assert results[0]["name"] == "alpha"
    finally:
        import shutil
        shutil.rmtree(logs.LOGS_DIR, ignore_errors=True)


def test_search_logs_limit():
    logs.LOGS_DIR = tempfile.mkdtemp(prefix="_armada_test_logs_")
    try:
        for i in range(10):
            logs.log_event("many", "ping", {"n": i})
        results = logs.search_logs("ping", limit=3)
        assert len(results) == 3
    finally:
        import shutil
        shutil.rmtree(logs.LOGS_DIR, ignore_errors=True)


def test_log_report():
    logs.LOGS_DIR = tempfile.mkdtemp(prefix="_armada_test_logs_")
    try:
        logs.log_report("reporter", "active", "doing work")
        entries = logs.get_node_logs("reporter")
        assert len(entries) == 1
        assert entries[0]["type"] == "report"
        assert entries[0]["data"]["status"] == "active"
        assert entries[0]["data"]["message"] == "doing work"
    finally:
        import shutil
        shutil.rmtree(logs.LOGS_DIR, ignore_errors=True)


def test_log_create():
    logs.LOGS_DIR = tempfile.mkdtemp(prefix="_armada_test_logs_")
    try:
        logs.log_create("new-node", "claude", "my-proj")
        entries = logs.get_node_logs("new-node")
        assert len(entries) == 1
        assert entries[0]["type"] == "create"
        assert entries[0]["data"]["agent_type"] == "claude"
        assert entries[0]["data"]["project"] == "my-proj"
    finally:
        import shutil
        shutil.rmtree(logs.LOGS_DIR, ignore_errors=True)


def test_log_kill():
    logs.LOGS_DIR = tempfile.mkdtemp(prefix="_armada_test_logs_")
    try:
        logs.log_kill("dying-node")
        entries = logs.get_node_logs("dying-node")
        assert len(entries) == 1
        assert entries[0]["type"] == "kill"
    finally:
        import shutil
        shutil.rmtree(logs.LOGS_DIR, ignore_errors=True)


def test_log_send():
    logs.LOGS_DIR = tempfile.mkdtemp(prefix="_armada_test_logs_")
    try:
        logs.log_send("target", "git status")
        entries = logs.get_node_logs("target")
        assert len(entries) == 1
        assert entries[0]["type"] == "send"
        assert entries[0]["data"]["command"] == "git status"
    finally:
        import shutil
        shutil.rmtree(logs.LOGS_DIR, ignore_errors=True)


def test_log_attach():
    logs.LOGS_DIR = tempfile.mkdtemp(prefix="_armada_test_logs_")
    try:
        logs.log_attach("attachable")
        entries = logs.get_node_logs("attachable")
        assert len(entries) == 1
        assert entries[0]["type"] == "attach"
    finally:
        import shutil
        shutil.rmtree(logs.LOGS_DIR, ignore_errors=True)


def test_log_health():
    logs.LOGS_DIR = tempfile.mkdtemp(prefix="_armada_test_logs_")
    try:
        logs.log_health("sick", dead=True)
        entries = logs.get_node_logs("sick")
        assert len(entries) == 1
        assert entries[0]["type"] == "health"
        assert entries[0]["data"]["dead"] is True
    finally:
        import shutil
        shutil.rmtree(logs.LOGS_DIR, ignore_errors=True)


def test_log_recover():
    logs.LOGS_DIR = tempfile.mkdtemp(prefix="_armada_test_logs_")
    try:
        logs.log_recover("revived")
        entries = logs.get_node_logs("revived")
        assert len(entries) == 1
        assert entries[0]["type"] == "recover"
    finally:
        import shutil
        shutil.rmtree(logs.LOGS_DIR, ignore_errors=True)


def test_log_server_start_stop():
    logs.LOGS_DIR = tempfile.mkdtemp(prefix="_armada_test_logs_")
    try:
        logs.log_server_start()
        logs.log_server_stop()
        server_log = os.path.join(logs.LOGS_DIR, "_server.jsonl")
        assert os.path.exists(server_log)
        with open(server_log) as f:
            entries = [json.loads(line) for line in f]
        assert len(entries) == 2
        assert entries[0]["type"] == "server_start"
        assert entries[1]["type"] == "server_stop"
    finally:
        import shutil
        shutil.rmtree(logs.LOGS_DIR, ignore_errors=True)


def test_rotate_logs():
    logs.LOGS_DIR = tempfile.mkdtemp(prefix="_armada_test_logs_")
    try:
        logs.log_event("big-node", "data", {"payload": "x" * 50})
        logs.rotate_logs(max_size_mb=0)  # force rotation
        log_path = os.path.join(logs.LOGS_DIR, "big-node.jsonl")
        gz_path = log_path + ".gz"
        assert not os.path.exists(log_path) or os.path.exists(gz_path)
    finally:
        import shutil
        shutil.rmtree(logs.LOGS_DIR, ignore_errors=True)


def test_search_logs_empty_query():
    logs.LOGS_DIR = tempfile.mkdtemp(prefix="_armada_test_logs_")
    try:
        logs.log_event("x", "test", {})
        results = logs.search_logs("", limit=10)
        assert len(results) >= 0
        results = logs.search_logs("zzz_nonexistent", limit=10)
        assert results == []
    finally:
        import shutil
        shutil.rmtree(logs.LOGS_DIR, ignore_errors=True)
