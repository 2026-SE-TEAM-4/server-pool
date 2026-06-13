"""sim 모듈 단위 테스트."""

from agent import sim


def test_current_mode_defaults_to_stable_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(sim, "MODE_PATH", str(tmp_path / "absent"))
    monkeypatch.setattr(sim, "DEFAULT_MODE", "stable")
    assert sim.current_mode() == "stable"


def test_current_mode_reads_valid_file(tmp_path, monkeypatch):
    path = tmp_path / "mode"
    path.write_text("real\n")
    monkeypatch.setattr(sim, "MODE_PATH", str(path))
    assert sim.current_mode() == "real"


def test_current_mode_rejects_unknown(tmp_path, monkeypatch):
    path = tmp_path / "mode"
    path.write_text("bogus")
    monkeypatch.setattr(sim, "MODE_PATH", str(path))
    monkeypatch.setattr(sim, "DEFAULT_MODE", "stable")
    assert sim.current_mode() == "stable"


def test_read_pct_file_clamps_and_validates(tmp_path):
    good = tmp_path / "g"
    good.write_text("73.5")
    assert sim.read_pct_file(str(good)) == 73.5
    bad = tmp_path / "b"
    bad.write_text("150")
    assert sim.read_pct_file(str(bad)) is None
    assert sim.read_pct_file(str(tmp_path / "absent")) is None


def test_mean_revert_stays_in_bounds_and_near_baseline():
    s = sim.MeanRevertSim("cpu:1", baseline=80.0, low=5.0, high=95.0)
    values = [s.step(80.0) for _ in range(200)]
    assert all(5.0 <= v <= 95.0 for v in values)
    # 평균회귀이므로 장기 평균이 기준선 근처에 머문다.
    assert 65.0 <= (sum(values) / len(values)) <= 95.0


def test_mean_revert_is_deterministic():
    a = sim.MeanRevertSim("cpu:1", 50.0, 5.0, 95.0)
    b = sim.MeanRevertSim("cpu:1", 50.0, 5.0, 95.0)
    assert [a.step(50.0) for _ in range(10)] == [b.step(50.0) for _ in range(10)]
