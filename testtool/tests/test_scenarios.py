import random

from app import scenarios as sc
from app.scenarios import CascadingFailure, MemoryLeak


def test_memory_leak_ramps_then_oom():
    eng = MemoryLeak([1, 2], duration_s=10, start_pct=40, max_pct=99, oom_hold_s=3)
    rng = random.Random(0)
    running = {1, 2}
    # 초반: 대상 선택 + load_ram 상승
    a0 = eng.tick(0, running, rng)
    kinds0 = [x.kind for x in a0]
    assert "load_ram" in kinds0
    target = a0[0].server_id
    # 램프 진행 중 값이 단조 증가
    v1 = next(x.value for x in eng.tick(2, running, rng) if x.kind == "load_ram")
    v2 = next(x.value for x in eng.tick(6, running, rng) if x.kind == "load_ram")
    assert v2 > v1
    # 임계 도달 시 stop 발생
    acts = eng.tick(10, running, rng)
    assert any(x.kind == "stop" and x.server_id == target for x in acts)


def test_memory_leak_done_after_restart():
    eng = MemoryLeak([1], duration_s=4, start_pct=40, max_pct=99, oom_hold_s=2)
    rng = random.Random(0)
    running = {1}
    for t in range(0, 5):
        eng.tick(t, running, rng)
    # oom_hold 경과 후 start+revert, done
    later = eng.tick(20, running, rng)
    assert any(x.kind == "start" for x in later)
    assert eng.is_done(20)


def test_cascading_starts_with_a_stop():
    eng = CascadingFailure([1, 2, 3], duration_s=30, step_every_s=5)
    rng = random.Random(1)
    acts = eng.tick(0, {1, 2, 3}, rng)
    assert len(acts) == 1 and acts[0].kind == "stop"


def test_cascading_loads_remaining_servers():
    eng = CascadingFailure([1, 2, 3], duration_s=30, step_every_s=5)
    rng = random.Random(1)
    eng.tick(0, {1, 2, 3}, rng)          # 한 대 정지
    acts = eng.tick(5, {1, 2, 3}, rng)   # 나머지 부하
    loaded = {x.server_id for x in acts if x.kind in ("load_cpu", "load_ram")}
    assert len(loaded) >= 1


def test_cascading_reverts_after_duration():
    eng = CascadingFailure([1, 2], duration_s=10, step_every_s=5)
    rng = random.Random(1)
    eng.tick(0, {1, 2}, rng)
    acts = eng.tick(10, {1, 2}, rng)
    assert any(x.kind == "revert" for x in acts)
    assert eng.is_done(10)


def test_overload_all_loads_every_running_server_then_reverts():
    engine = sc.OverloadAll(server_ids=[1, 2], intensity=80, duration_s=60)
    start = engine.tick(elapsed_s=0, running={1, 2}, rng=random.Random(0))
    kinds = {(a.kind, a.server_id) for a in start}
    assert ("load_cpu", 1) in kinds
    assert ("load_ram", 2) in kinds
    # 만료 시 전체 revert
    end = engine.tick(elapsed_s=60, running={1, 2}, rng=random.Random(0))
    assert all(a.kind == "revert" for a in end)
    assert {a.server_id for a in end} == {1, 2}


def test_overload_all_is_done_after_duration():
    engine = sc.OverloadAll(server_ids=[1], intensity=80, duration_s=30)
    engine.tick(elapsed_s=0, running={1}, rng=random.Random(0))
    assert engine.is_done(elapsed_s=29) is False
    assert engine.is_done(elapsed_s=30) is True


def test_random_stop_stops_a_running_server():
    engine = sc.RandomStop(
        server_ids=[1, 2, 3], duration_s=300, stop_min_s=10, stop_max_s=60, every_s=5
    )
    actions = engine.tick(elapsed_s=5, running={1, 2, 3}, rng=random.Random(1))
    stops = [a for a in actions if a.kind == "stop"]
    assert len(stops) == 1
    assert stops[0].server_id in {1, 2, 3}
    assert 10 <= stops[0].value <= 60  # 정지 시간(초)


def test_random_stop_schedules_restart_after_value():
    engine = sc.RandomStop(
        server_ids=[1], duration_s=300, stop_min_s=10, stop_max_s=10, every_s=5
    )
    engine.tick(elapsed_s=5, running={1}, rng=random.Random(1))
    # 10초 뒤 재시작 예약. 정지 직후엔 start 없음, 15초엔 start.
    assert [a.kind for a in engine.tick(elapsed_s=6, running=set(), rng=random.Random(1))] == []
    restart = engine.tick(elapsed_s=15, running=set(), rng=random.Random(1))
    assert any(a.kind == "start" and a.server_id == 1 for a in restart)


def test_random_stop_deterministic_with_seed():
    def run():
        engine = sc.RandomStop(
            server_ids=[1, 2, 3], duration_s=300, stop_min_s=10, stop_max_s=60, every_s=5
        )
        return [a.server_id for a in engine.tick(5, {1, 2, 3}, random.Random(42)) if a.kind == "stop"]
    assert run() == run()
