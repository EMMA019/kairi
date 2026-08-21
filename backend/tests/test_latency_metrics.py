from app.core.latency_metrics import (
    LatencyProbe,
    get_latency_snapshot,
    record_latency,
    reset_latency_metrics,
)


def test_ttft_percentiles_and_skip_rate(tmp_path, monkeypatch):
    import app.core.latency_metrics as lm

    monkeypatch.setattr(lm, "_METRICS_PATH", tmp_path / "latency_metrics.json")
    reset_latency_metrics()
    record_latency(
        first_sse_ms=10,
        first_chunk_ms=100,
        search_ms=0,
        supervisor_ms=0,
        total_ms=120,
        supervisor_skipped=True,
        supervisor_loops=1,
    )
    record_latency(
        first_sse_ms=20,
        first_chunk_ms=300,
        search_ms=50,
        supervisor_ms=80,
        total_ms=400,
        supervisor_skipped=False,
        supervisor_loops=2,
    )
    snap = get_latency_snapshot()
    assert snap["sample_count"] == 2
    assert snap["ttft_p50_ms"] == 100
    assert snap["supervisor_skip_count"] == 1
    assert snap["supervisor_skip_rate"] == 0.5
    assert snap["avg_supervisor_loops"] == 1.5
    assert (tmp_path / "latency_metrics.json").exists()


def test_probe_records_first_chunk():
    reset_latency_metrics()
    probe = LatencyProbe()
    probe.observe_sse('data: {"type": "status", "status": "thinking"}\n\n')
    probe.observe_sse('data: {"type": "chunk", "content": "hi"}\n\n')
    sample = probe.finish(supervisor_skipped=True, supervisor_loops=1)
    assert sample["first_sse_ms"] is not None
    assert sample["first_chunk_ms"] is not None
    assert sample["first_chunk_ms"] >= sample["first_sse_ms"]
    assert sample["supervisor_skipped"] is True
