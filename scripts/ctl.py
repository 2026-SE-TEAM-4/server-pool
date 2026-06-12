#!/usr/bin/env python3
"""서버풀 대화형 제어 CLI.

실행: python scripts/ctl.py
메뉴를 arrow key로 탐색하고 Enter로 선택한다.
"""

import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

import questionary
from questionary import Style
from rich.console import Console
from rich.table import Table

COMPOSE_FILE = Path(__file__).parent.parent / "docker-compose.yml"
SERVER_IDS = [1, 2, 3, 4, 5]
PORT_BASE = 9100

PRESETS = {
    "full      (CPU 100  MEM 100  GPU 100  NET 100)": {"cpu": 100, "mem": 100, "gpu": 100, "net": 100},
    "high      (CPU  90  MEM  85  GPU  80  NET  70)": {"cpu": 90,  "mem": 85,  "gpu": 80,  "net": 70},
    "medium    (CPU  70  MEM  70  GPU  70  NET  50)": {"cpu": 70,  "mem": 70,  "gpu": 70,  "net": 50},
    "low       (CPU  20  MEM  30  GPU  15  NET  10)": {"cpu": 20,  "mem": 30,  "gpu": 15,  "net": 10},
    "idle      (CPU   5  MEM  20  GPU   0  NET   2)": {"cpu": 5,   "mem": 20,  "gpu": 0,   "net": 2},
    "cpu-spike (CPU 100  MEM  40  GPU  30  NET  20)": {"cpu": 100, "mem": 40,  "gpu": 30,  "net": 20},
    "mem-spike (CPU  20  MEM 100  GPU  30  NET  20)": {"cpu": 20,  "mem": 100, "gpu": 30,  "net": 20},
    "gpu-spike (CPU  20  MEM  40  GPU 100  NET  20)": {"cpu": 20,  "mem": 40,  "gpu": 100, "net": 20},
    "net-spike (CPU  20  MEM  40  GPU  30  NET 100)": {"cpu": 20,  "mem": 40,  "gpu": 30,  "net": 100},
    "커스텀 입력...": None,
}

STYLE = Style([
    ("qmark",     "fg:#00b4d8 bold"),
    ("question",  "bold"),
    ("answer",    "fg:#90e0ef bold"),
    ("pointer",   "fg:#00b4d8 bold"),
    ("highlighted","fg:#00b4d8 bold"),
    ("selected",  "fg:#caf0f8"),
    ("separator", "fg:#4a4e69"),
    ("instruction","fg:#888888"),
])

console = Console()


# ── HTTP 헬퍼 ─────────────────────────────────────────────────────────────────

def _get(url: str) -> Optional[dict]:
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            return json.loads(r.read())
    except Exception:
        return None


def _post(url: str, payload: dict) -> Optional[dict]:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=2) as r:
            return json.loads(r.read())
    except Exception:
        return None


def _port(sid: int) -> int:
    return PORT_BASE + sid


# ── 화면 출력 ──────────────────────────────────────────────────────────────────

def show_status() -> None:
    console.rule("[bold cyan]서버풀 상태[/bold cyan]")
    table = Table(show_lines=True, border_style="cyan")
    table.add_column("ID",   justify="center", style="bold")
    table.add_column("Port", justify="center")
    table.add_column("상태", justify="center")
    table.add_column("CPU",  justify="right")
    table.add_column("MEM",  justify="right")
    table.add_column("GPU",  justify="right")
    table.add_column("NET",  justify="right")

    for sid in SERVER_IDS:
        port = _port(sid)
        health = _get(f"http://localhost:{port}/health")
        metrics = _get(f"http://localhost:{port}/metrics")
        if health is None:
            table.add_row(
                str(sid), str(port),
                "[red]DOWN[/red]", "-", "-", "-", "-",
            )
        else:
            gpu_val = metrics.get("gpuUsage") if metrics else None
            table.add_row(
                str(sid), str(port),
                "[green]UP[/green]",
                f"{metrics['cpuUsage']}%" if metrics else "-",
                f"{metrics['memUsage']}%" if metrics else "-",
                f"{gpu_val}%" if gpu_val is not None else "-",
                f"{metrics['netUsage']}%" if metrics else "-",
            )
    console.print(table)


def _ok(msg: str) -> None:
    console.print(f"  [green]✓[/green] {msg}")


def _warn(msg: str) -> None:
    console.print(f"  [yellow]![/yellow] {msg}")


# ── 서버 선택 헬퍼 ─────────────────────────────────────────────────────────────

def _ask_servers(prompt: str) -> list[int]:
    choices = [questionary.Choice(f"agent-{sid}  (port {_port(sid)})", value=sid) for sid in SERVER_IDS]
    choices.append(questionary.Choice("전체 (all)", value=0))
    answer = questionary.select(prompt, choices=choices, style=STYLE).ask()
    if answer is None:
        return []
    return SERVER_IDS if answer == 0 else [answer]


# ── 서브메뉴: 서버 제어 ────────────────────────────────────────────────────────

def menu_control() -> None:
    action = questionary.select(
        "액션을 선택하세요",
        choices=[
            questionary.Choice("기동  (docker compose up -d)", value="up"),
            questionary.Choice("재시작", value="restart"),
            questionary.Choice("강제 종료  (SIGKILL)", value="crash"),
            questionary.Choice("← 돌아가기", value="back"),
        ],
        style=STYLE,
    ).ask()

    if action in (None, "back"):
        return

    if action == "up":
        console.print("  모든 컨테이너를 기동합니다...")
        cmd = ["docker", "compose", "-f", str(COMPOSE_FILE), "up", "-d"]
        subprocess.run(cmd, check=False)
        return

    ids = _ask_servers("대상 서버를 선택하세요")
    if not ids:
        return

    for sid in ids:
        container = f"server-pool-agent-{sid}-1"
        if action == "crash":
            result = subprocess.run(["docker", "kill", container], capture_output=True, text=True)
            if result.returncode == 0:
                _ok(f"agent-{sid} KILLED")
            else:
                _warn(f"agent-{sid} 종료 실패 (이미 정지됐거나 없음)")
        elif action == "restart":
            cmd = ["docker", "compose", "-f", str(COMPOSE_FILE), "restart", f"agent-{sid}"]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                _ok(f"agent-{sid} 재시작 완료")
            else:
                _warn(f"agent-{sid} 재시작 실패")


# ── 서브메뉴: 부하 주입 ────────────────────────────────────────────────────────

def menu_inject() -> None:
    ids = _ask_servers("부하를 주입할 서버를 선택하세요")
    if not ids:
        return

    preset_key = questionary.select(
        "프리셋을 선택하세요",
        choices=list(PRESETS.keys()),
        style=STYLE,
    ).ask()
    if preset_key is None:
        return

    payload = PRESETS[preset_key]

    if payload is None:
        # 커스텀 입력
        def _ask_pct(label: str, default: str) -> float:
            val = questionary.text(
                f"{label} % (0~100)", default=default,
                validate=lambda v: v.replace(".", "", 1).isdigit() and 0 <= float(v) <= 100
                    or "0~100 사이 숫자를 입력하세요",
                style=STYLE,
            ).ask()
            return float(val) if val is not None else float(default)

        payload = {
            "cpu": _ask_pct("CPU", "50"),
            "mem": _ask_pct("MEM", "50"),
            "gpu": _ask_pct("GPU", "50"),
            "net": _ask_pct("NET", "20"),
        }

    for sid in ids:
        port = _port(sid)
        result = _post(f"http://localhost:{port}/inject", payload)
        if result:
            inj = result["injected"]
            _ok(f"agent-{sid}  CPU={inj['cpu']}%  MEM={inj['mem']}%  GPU={inj.get('gpu')}%  NET={inj.get('net')}%")
        else:
            _warn(f"agent-{sid} 응답 없음 (DOWN?)")


# ── 서브메뉴: 오버라이드 해제 ──────────────────────────────────────────────────

def menu_reset() -> None:
    ids = _ask_servers("오버라이드를 해제할 서버를 선택하세요")
    if not ids:
        return
    for sid in ids:
        port = _port(sid)
        result = _post(f"http://localhost:{port}/reset", {})
        if result:
            _ok(f"agent-{sid} 오버라이드 해제 완료")
        else:
            _warn(f"agent-{sid} 응답 없음 (DOWN?)")


# ── 메인 루프 ──────────────────────────────────────────────────────────────────

def main() -> None:
    console.print("\n[bold cyan]서버풀 제어 CLI[/bold cyan]  (Ctrl+C 로 종료)\n")

    while True:
        show_status()
        console.print()

        action = questionary.select(
            "메뉴를 선택하세요",
            choices=[
                questionary.Choice("상태 새로고침",        value="status"),
                questionary.Choice("서버 제어  (기동 / 재시작 / 강제종료)", value="control"),
                questionary.Choice("부하 주입  (CPU / MEM / GPU / NET 오버라이드)", value="inject"),
                questionary.Choice("오버라이드 해제",      value="reset"),
                questionary.Choice("종료",                 value="quit"),
            ],
            style=STYLE,
        ).ask()

        console.print()

        if action in (None, "quit"):
            console.print("[dim]종료합니다.[/dim]")
            sys.exit(0)
        elif action == "status":
            pass  # 루프 상단에서 자동으로 다시 출력됨
        elif action == "control":
            menu_control()
        elif action == "inject":
            menu_inject()
        elif action == "reset":
            menu_reset()

        console.print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[dim]종료합니다.[/dim]")
        sys.exit(0)
