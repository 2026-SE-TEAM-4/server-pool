"""카오스 시나리오: 순수 결정 엔진 + Qt 러너.

엔진(OverloadAll/RandomStop/RandomSpike)은 Qt를 모른다. tick(elapsed, running, rng)이
이번 틱에 수행할 Action 목록을 돌려준다. RNG는 외부 주입이라 시드 고정 시 결정론적이다.
러너(ChaosRunner)는 QTimer로 매초 tick을 호출하고 Action을 docker/injector로 디스패치한다.
중지 시 모든 부하/정지를 즉시 원복한다.
"""

from dataclasses import dataclass


@dataclass
class Action:
    kind: str  # load_cpu | load_ram | gpu | revert | stop | start
    server_id: int
    value: float | None = None  # 부하 %, GPU %, 또는 정지 시간(초)


class OverloadAll:
    """실행 중 모든 서버에 CPU/RAM 고부하를 duration_s 동안. 만료 시 전체 revert."""

    def __init__(self, server_ids, intensity, duration_s):
        self._ids = list(server_ids)
        self._intensity = intensity
        self._duration = duration_s
        self._applied = False
        self._reverted = False

    def tick(self, elapsed_s, running, rng):
        if elapsed_s >= self._duration:
            if self._reverted:
                return []
            self._reverted = True
            return [Action("revert", sid) for sid in self._ids]
        if self._applied:
            return []
        self._applied = True
        actions = []
        for sid in self._ids:
            if sid in running:
                actions.append(Action("load_cpu", sid, self._intensity))
                actions.append(Action("load_ram", sid, self._intensity))
        return actions

    def is_done(self, elapsed_s):
        return elapsed_s >= self._duration


class RandomStop:
    """every_s 마다 랜덤 실행 서버 하나를 stop_min~stop_max초 정지 후 재시작. duration_s까지."""

    def __init__(self, server_ids, duration_s, stop_min_s, stop_max_s, every_s):
        self._ids = list(server_ids)
        self._duration = duration_s
        self._stop_min = stop_min_s
        self._stop_max = stop_max_s
        self._every = every_s
        self._restart_at: dict[int, float] = {}  # server_id → 재시작 예정 elapsed

    def tick(self, elapsed_s, running, rng):
        actions = []
        # 재시작 예정 처리
        for sid, due in list(self._restart_at.items()):
            if elapsed_s >= due:
                actions.append(Action("start", sid))
                del self._restart_at[sid]
        # 정지 시도(주기마다, duration 내에서만)
        if elapsed_s > 0 and elapsed_s % self._every == 0 and elapsed_s < self._duration:
            candidates = [s for s in self._ids if s in running and s not in self._restart_at]
            if candidates:
                target = rng.choice(candidates)
                hold = rng.randint(self._stop_min, self._stop_max)
                self._restart_at[target] = elapsed_s + hold
                actions.append(Action("stop", target, hold))
        return actions

    def is_done(self, elapsed_s):
        # duration 경과 + 예약된 재시작이 모두 끝나야 종료
        return elapsed_s >= self._duration and not self._restart_at


class RandomSpike:
    """every_s 마다 랜덤 서버에 랜덤 강도 부하를 랜덤 시간 주입 후 자동 revert. duration_s까지."""

    def __init__(self, server_ids, duration_s, every_s, spike_min_s=10, spike_max_s=40):
        self._ids = list(server_ids)
        self._duration = duration_s
        self._every = every_s
        self._spike_min = spike_min_s
        self._spike_max = spike_max_s
        self._revert_at: dict[int, float] = {}

    def tick(self, elapsed_s, running, rng):
        actions = []
        for sid, due in list(self._revert_at.items()):
            if elapsed_s >= due:
                actions.append(Action("revert", sid))
                del self._revert_at[sid]
        if elapsed_s > 0 and elapsed_s % self._every == 0 and elapsed_s < self._duration:
            candidates = [s for s in self._ids if s in running and s not in self._revert_at]
            if candidates:
                target = rng.choice(candidates)
                intensity = rng.choice([50, 80, 100])
                hold = rng.randint(self._spike_min, self._spike_max)
                self._revert_at[target] = elapsed_s + hold
                actions.append(Action("load_cpu", target, intensity))
        return actions

    def is_done(self, elapsed_s):
        return elapsed_s >= self._duration and not self._revert_at


class MemoryLeak:
    """대상 1대의 RAM을 start_pct→max_pct로 duration 동안 선형 상승.
    임계 도달 시 stop(OOM 모사)→oom_hold초 뒤 start·revert.
    """

    def __init__(self, server_ids, duration_s, start_pct=40, max_pct=99, oom_hold_s=8):
        self._ids = list(server_ids)
        self._duration = max(1, duration_s)
        self._start = start_pct
        self._max = max_pct
        self._oom_hold = oom_hold_s
        self._target = None
        self._restart_at = None
        self._oom = False
        self._done = False

    def tick(self, elapsed_s, running, rng):
        actions = []
        if self._target is None:
            candidates = [s for s in self._ids if s in running]
            if not candidates:
                return []
            self._target = rng.choice(candidates)
        if self._restart_at is not None:
            if elapsed_s >= self._restart_at:
                self._restart_at = None
                self._done = True
                return [Action("start", self._target), Action("revert", self._target)]
            return []
        if self._oom:
            return []
        ramp = min(1.0, elapsed_s / self._duration)
        pct = int(self._start + (self._max - self._start) * ramp)
        actions.append(Action("load_ram", self._target, pct))
        if pct >= self._max:
            self._oom = True
            self._restart_at = elapsed_s + self._oom_hold
            actions.append(Action("stop", self._target, self._oom_hold))
        return actions

    def is_done(self, elapsed_s):
        return self._done


class CascadingFailure:
    """1대 정지로 시작, 남은 서버 CPU/RAM을 step_every_s마다 단계적으로 상승(부하 재분배).
    duration 만료 시 전체 revert·정지 서버 start.
    """

    def __init__(self, server_ids, duration_s, step_every_s=8,
                 base_pct=55, step_pct=12, max_pct=98):
        self._ids = list(server_ids)
        self._duration = duration_s
        self._every = max(1, step_every_s)
        self._base = base_pct
        self._step = step_pct
        self._max = max_pct
        self._downed = None
        self._reverted = False

    def tick(self, elapsed_s, running, rng):
        if elapsed_s >= self._duration:
            if self._reverted:
                return []
            self._reverted = True
            acts = [Action("revert", s) for s in self._ids]
            if self._downed is not None:
                acts.append(Action("start", self._downed))
            return acts
        if self._downed is None:
            candidates = [s for s in self._ids if s in running]
            if not candidates:
                return []
            self._downed = rng.choice(candidates)
            return [Action("stop", self._downed)]
        actions = []
        if elapsed_s > 0 and elapsed_s % self._every == 0:
            stage = elapsed_s // self._every
            pct = min(self._max, self._base + self._step * (stage - 1))
            for s in self._ids:
                if s != self._downed and s in running:
                    actions.append(Action("load_cpu", s, pct))
                    actions.append(Action("load_ram", s, pct))
        return actions

    def is_done(self, elapsed_s):
        return elapsed_s >= self._duration and self._reverted


from PyQt6.QtCore import QObject, QRunnable, QThreadPool, QTimer, pyqtSignal  # noqa: E402


class _ChaosJob(QRunnable):
    """카오스 액션의 블로킹 docker/injector 호출을 UI 스레드 밖에서 실행한다."""

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def run(self):
        try:
            self._fn()
        except Exception:
            pass


class ChaosRunner(QObject):
    """엔진을 매초 구동하고 Action을 docker/injector로 디스패치한다.

    running 집합은 폴러 스냅샷으로 갱신된다(set_running). 중지 시 그동안 부하/정지한
    모든 서버를 즉시 원복한다.
    """

    log = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, engine, docker, injector, rng, parent=None):
        super().__init__(parent)
        self._engine = engine
        self._docker = docker
        self._injector = injector
        self._rng = rng
        self._elapsed = 0
        self._running: set[int] = set()
        self._touched: set[int] = set()  # 부하/정지를 가한 서버(원복 대상)
        self._pool = QThreadPool.globalInstance()
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)

    def set_running(self, running):
        self._running = set(running)

    def _run_async(self, fn):
        self._pool.start(_ChaosJob(fn))

    def start(self):
        self._elapsed = 0
        self._timer.start()

    def _tick(self):
        actions = self._engine.tick(self._elapsed, self._running, self._rng)
        for a in actions:
            self._dispatch(a)
        self._elapsed += 1
        if self._engine.is_done(self._elapsed):
            self.stop()

    def _dispatch(self, a):
        self._touched.add(a.server_id)
        sid = a.server_id
        if a.kind == "load_cpu":
            pct = int(a.value)
            self._run_async(lambda s=sid, v=pct: self._injector.apply_cpu(s, v))
            self.log.emit(f"agent-{sid} CPU {pct}% 부하 주입")
        elif a.kind == "load_ram":
            pct = int(a.value)
            self._run_async(lambda s=sid, v=pct: self._injector.apply_ram(s, v))
            self.log.emit(f"agent-{sid} RAM {pct}% 부하 주입")
        elif a.kind == "gpu":
            pct = int(a.value)
            self._run_async(lambda s=sid, v=pct: self._injector.set_gpu(s, v))
            self.log.emit(f"agent-{sid} GPU {pct}% 설정")
        elif a.kind == "load_net":
            pct = int(a.value)
            self._run_async(lambda s=sid, v=pct: self._injector.apply_net(s, v))
            self.log.emit(f"agent-{sid} NET {pct}% 부하 주입")
        elif a.kind == "revert":
            self._run_async(lambda s=sid: self._injector.revert_all(s))
            self.log.emit(f"agent-{sid} 부하 원복")
        elif a.kind == "stop":
            self._run_async(lambda s=sid: self._docker.stop(s))
            self.log.emit(f"agent-{sid} 정지 ({int(a.value)}초)")
        elif a.kind == "start":
            self._run_async(lambda s=sid: self._docker.start(s))
            self.log.emit(f"agent-{sid} 재시작")

    def stop(self):
        self._timer.stop()
        for sid in self._touched:
            self._run_async(
                lambda s=sid: (self._injector.revert_all(s), self._docker.start(s))
            )
        self.log.emit("카오스 중지 — 전체 원복")
        self._touched.clear()
        self.finished.emit()
