"""에이전트 환경 설정.

PORT와 SERVER_ID는 컨테이너마다 다르게 주입된다(compose의 environment).
SERVER_SPECS는 서버 ID별 정적 하드웨어 사양을 정의한다. 에이전트가 응답하는
/info 엔드포인트와 GPU 시뮬레이션 여부에 이 값을 사용한다.
경량 유지를 위해 추가 의존성 없이 os.environ만 사용한다.
"""

import os

PORT = int(os.getenv("PORT", "9101"))
SERVER_ID = int(os.getenv("SERVER_ID", "1"))

# 서버 ID별 정적 하드웨어 사양.
# cpu_cores: 물리 코어 수(하이퍼스레딩 포함 논리 코어가 아닌 물리 기준).
# gpu_model: None이면 GPU 미탑재, 시뮬레이션도 비활성화된다.
SERVER_SPECS: dict[int, dict] = {
    1: {
        "hostname": "gpu-a100-01",
        "cpu_model": "AMD EPYC 7763",
        "cpu_cores": 64,
        "ram_gb": 256,
        "gpu_model": "NVIDIA A100 80GB",
        "gpu_count": 2,
        "gpu_vram_gb": 80,
        "storage": "2TB NVMe SSD",
        "net_cap_mbps": 25000,
        "group": "HPC GPU 클러스터",
        "ip": "10.0.0.1",
    },
    2: {
        "hostname": "gpu-rtx4090-01",
        "cpu_model": "Intel Xeon W-3375",
        "cpu_cores": 38,
        "ram_gb": 128,
        "gpu_model": "NVIDIA RTX 4090 24GB",
        "gpu_count": 4,
        "gpu_vram_gb": 24,
        "storage": "1TB NVMe SSD",
        "net_cap_mbps": 10000,
        "group": "GPU 워크스테이션",
        "ip": "10.0.0.2",
    },
    3: {
        "hostname": "gpu-rtx3090-01",
        "cpu_model": "AMD Threadripper PRO 5975WX",
        "cpu_cores": 32,
        "ram_gb": 128,
        "gpu_model": "NVIDIA RTX 3090 24GB",
        "gpu_count": 2,
        "gpu_vram_gb": 24,
        "storage": "2TB NVMe SSD",
        "net_cap_mbps": 10000,
        "group": "GPU 워크스테이션",
        "ip": "10.0.0.3",
    },
    4: {
        "hostname": "gpu-t4-01",
        "cpu_model": "Intel Xeon Gold 6326",
        "cpu_cores": 16,
        "ram_gb": 64,
        "gpu_model": "NVIDIA Tesla T4 16GB",
        "gpu_count": 1,
        "gpu_vram_gb": 16,
        "storage": "1TB NVMe SSD",
        "net_cap_mbps": 10000,
        "group": "추론 서버",
        "ip": "10.0.0.4",
    },
    5: {
        "hostname": "cpu-xeon-01",
        "cpu_model": "Intel Xeon Platinum 8480+ × 2",
        "cpu_cores": 112,
        "ram_gb": 512,
        "gpu_model": None,
        "gpu_count": 0,
        "gpu_vram_gb": 0,
        "storage": "4TB NVMe SSD RAID",
        "net_cap_mbps": 100000,
        "group": "CPU HPC 클러스터",
        "ip": "10.0.0.5",
    },
    6: {
        "hostname": "cpu-epyc-01",
        "cpu_model": "AMD EPYC 9654",
        "cpu_cores": 96,
        "ram_gb": 384,
        "gpu_model": None,
        "gpu_count": 0,
        "gpu_vram_gb": 0,
        "storage": "3TB NVMe SSD",
        "net_cap_mbps": 25000,
        "group": "CPU HPC 클러스터",
        "ip": "10.0.0.6",
    },
}

# 현재 서버 사양. SERVER_ID가 스펙에 없으면 빈 dict.
SPEC: dict = SERVER_SPECS.get(SERVER_ID, {})

# 네트워크 대역폭(Mbps): 환경 변수 우선, 없으면 스펙 기본값, 그것도 없으면 1000.
NET_CAP_MBPS = float(os.getenv("NET_CAP_MBPS", str(SPEC.get("net_cap_mbps", 1000))))

# GPU 시뮬레이션: 스펙에 gpu_model이 있으면 기본 활성화, 없으면 비활성화.
_gpu_simulate_default = "true" if SPEC.get("gpu_model") else "false"
GPU_SIMULATE = os.getenv("GPU_SIMULATE", _gpu_simulate_default).lower() == "true"

# 기본 모드: 모드 파일(/tmp/agent_mode)이 없을 때 적용한다.
# stable=안정 합성(데모 기본), real=psutil 실측, randomwalk=±8% 랜덤워크.
# 베어메탈 실측 배포는 DEFAULT_MODE=real.
DEFAULT_MODE = os.getenv("DEFAULT_MODE", "stable")
