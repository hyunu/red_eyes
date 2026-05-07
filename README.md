# Red Eyes

로컬 AI CCTV 행동 분석 시스템. Mac Mini M1 8GB 환경에서 실시간으로 CCTV 영상을 분석하여 사람 행동을 감지하고, 자연어 요약 후 텔레그램으로 알림을 전송합니다.

## 특징

- **완전 로컬 실행**: 클라우드 의존 없음, Ollama 기반 VLM
- **M1 최적화**: MPS 가속, 5GB 이하 메모리 사용
- **이벤트 기반**: 사람 감지 시에만 분석 및 저장, 디스크 절약
- **자동 복구**: RTSP 끊김 자동 재연결, VLM 장애 시 fallback
- **알림**: 텔레그램으로 분석 요약 + 대표 이미지 전송

## 아키텍처

```
RTSP Stream ──▶ Frame Queue ──▶ YOLOv8n ──▶ EventTracker ──▶ VLM (Ollama)
                    │                │              │                  │
              (max 3 frames)  (adaptive skip)  (state machine)   (qwen2-vl:2b)
                                                                      │
                                                              Telegram Alert
```

## 시스템 요구사항

| 항목 | 요구사항 |
|---|---|
| 하드웨어 | Apple Mac Mini M1 (8GB RAM 권장) |
| OS | macOS 13+ (Ventura 이상) |
| Python | 3.11+ |
| Ollama | 설치 및 `qwen2-vl:2b` 모델 |
| RTSP | Tapo TC72 등 RTSP 지원 CCTV |

## 빠른 시작

### 1. 사전 준비

```bash
# Ollama 설치
brew install ollama
brew services start ollama

# VLM 모델 다운로드 (약 1.5GB)
ollama pull qwen2-vl:2b

# Python 3.11+ 확인
python3 --version
```

### 2. 설치

```bash
# 저장소 클론
git clone https://github.com/hyunu/red_eyes.git
cd red_eyes

# 가상환경 생성 및 활성화
python3 -v venv .venv
source .venv/bin/activate

# 의존성 설치
pip install -e ".[dev]"
```

### 3. 설정

```bash
# 환경변수 설정
cp .env.example .env
```

`.env` 파일 수정:

```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

`config/settings.yaml` 수정:

```yaml
rtsp:
  cameras:
    - id: "cam_01"
      name: "현관"
      url: "rtsp://admin:password@192.168.1.100:554/stream1"
      enabled: true
```

### 4. 실행

```bash
make run
```

또는 직접 실행:

```bash
python -m red_eyes.cli
```

### 5. 텔레그램 봇 설정

1. Telegram에서 [@BotFather](https://t.me/BotFather) 검색
2. `/newbot` 명령어로 새 봇 생성
3. 봇 토큰을 `.env`의 `TELEGRAM_BOT_TOKEN`에 입력
4. 봇에게 `/start` 메시지 전송
5. `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`에서 `chat.id` 확인
6. `chat.id`를 `.env`의 `TELEGRAM_CHAT_ID`에 입력

## Tapo TC72 RTSP 설정

Tapo TC72 카메라의 RTSP를 활성화하는 방법:

1. Tapo 앱에서 카메라 설정 진입
2. 고급 설정 → RTSP 활성화
3. RTSP 계정 생성 (ID/PW 설정)
4. RTSP URL 형식:
   ```
   rtsp://username:password@<카메라IP>:554/stream1
   ```
   - `stream1`: 고화질 (기본)
   - `stream2`: 저화질

설정 파일 예시:

```yaml
rtsp:
  cameras:
    - id: "front_door"
      name: "현관"
      url: "rtsp://admin:mysecretpassword@192.168.1.100:554/stream1"
      enabled: true
    - id: "backyard"
      name: "뒷마당"
      url: "rtsp://admin:mysecretpassword@192.168.1.101:554/stream1"
      enabled: true
```

## 설정 파일 상세

### config/settings.yaml

```yaml
system:
  device: "mps"              # mps (M1 GPU) 또는 cpu
  max_memory_gb: 5.0         # 최대 메모리 사용량
  log_level: "INFO"          # DEBUG, INFO, WARNING, ERROR
  log_file: "data/logs/red_eyes.log"

rtsp:
  cameras:                   # 카메라 목록
    - id: "cam_01"           # 고유 ID
      name: "현관"            # 표시 이름
      url: "rtsp://..."      # RTSP URL
      enabled: true          # 활성화 여부
  reconnect:
    initial_delay: 1.0       # 첫 재연결 대기 (초)
    max_delay: 300.0         # 최대 재연결 대기 (초)
    max_attempts: 100        # 최대 시도 횟수
  frame:
    target_width: 640        # 분석용 리사이즈
    target_height: 640
    max_queue_size: 3        # 프레임 큐 최대 크기

detection:
  model: "yolov8n.pt"        # YOLO 모델
  confidence: 0.5            # 감지 신뢰도 임계값
  device: "mps"              # mps 또는 cpu
  adaptive:
    idle_interval: 3.0       # 사람 없을 때 분석 간격 (초)
    active_interval: 0.5     # 사람 감지 시 분석 간격 (초)
    max_interval: 5.0        # 최대 분석 간격 (초)
    cpu_threshold: 0.7       # CPU 사용률 임계값

events:
  approach_threshold: 3.0    # 접근 이벤트 확인 시간 (초)
  loitering_threshold: 30    # 대기 이벤트 발생 시간 (초)
  delivery_threshold: 10     # 배달 이벤트 정지 시간 (초)
  patrol_min_moves: 3        # 배회 이벤트 방향 전환 횟수
  night_mode_start: "22:00"  # 야간 모드 시작
  night_mode_end: "06:00"    # 야간 모드 종료

vlm:
  provider: "ollama"
  model: "qwen2-vl:2b"       # 사용할 VLM 모델
  base_url: "http://localhost:11434"
  timeout: 30                # 분석 타임아웃 (초)
  max_images: 2              # 분석에 사용할 이미지 수
  prompt: |                  # 분석 프롬프트
    CCTV 영상을 분석하여 사람의 행동을 설명하세요.
    무엇을 했는지, 얼마나 머물렀는지, 물건 관련 행동이 있었는지 중점으로 설명하세요.
    한국어로 1-2 문장만 응답하세요.

telegram:
  bot_token: ""              # .env에서 오버라이드
  chat_id: ""                # .env에서 오버라이드
  rate_limit: 300            # 동일 이벤트 알림 간격 (초)
  max_images_per_alert: 2    # 알림당 이미지 수

storage:
  base_dir: "data/events"    # 이벤트 저장 위치
  max_disk_gb: 1.0           # 최대 디스크 사용량
  retention_days: 7          # 이벤트 보관 기간 (일)
  keyframes_per_event: 2     # 이벤트당 저장 이미지 수
  cleanup_interval: 3600     # 정리 실행 간격 (초)
```

## 이벤트 유형

| 이벤트 | 조건 | 설명 |
|---|---|---|
| `person_entered` | 사람이 화면 진입 | 카메라 영역에 첫 등장 |
| `approaching` | 3초간 접근 동작 | 카메라 쪽으로 다가옴 |
| `loitering` | 30초간 머무름 | 제자리 대기 |
| `delivery` | 10초간 정지 후 움직임 | 물건 내려놓음 |
| `patrolling` | 3회 이상 방향 전환 | 배회 행동 |
| `person_left` | 5초간 미감지 | 화면 이탈 |
| `night_movement` | 야간 시간대 감지 | 22:00~06:00 움직임 |

## 이벤트 쿨다운

동일 이벤트 중복 알림 방지를 위한 쿨다운:

| 이벤트 | 쿨다운 |
|---|---|
| person_entered | 120초 |
| approaching | 60초 |
| loitering | 180초 |
| delivery | 300초 |
| patrolling | 300초 |
| person_left | 60초 |
| night_movement | 300초 |

## 폴더 구조

```
red_eyes/
├── config/
│   └── settings.yaml          # 메인 설정
├── src/red_eyes/
│   ├── cli.py                 # 메인 오케스트레이터
│   ├── core/
│   │   ├── config.py          # Pydantic 설정
│   │   ├── models.py          # 데이터 모델
│   │   └── queue.py           # 프레임 큐
│   ├── capture/
│   │   └── rtsp.py            # RTSP 캡처
│   ├── detection/
│   │   └── person.py          # YOLO 감지
│   ├── events/
│   │   └── tracker.py         # 이벤트 추적
│   ├── vlm/
│   │   └── analyzer.py        # VLM 분석
│   ├── notification/
│   │   └── telegram.py        # 텔레그램 알림
│   ├── storage/
│   │   └── manager.py         # 저장 관리
│   └── utils/
│       ├── logger.py          # 로깅
│       └── memory.py          # 메모리 모니터링
├── data/
│   ├── events/                # 이벤트 저장
│   │   └── 2024-03-15/
│   │       └── abc12345/
│   │           ├── frame_001.jpg
│   │           ├── frame_002.jpg
│   │           └── metadata.json
│   └── logs/
│       └── red_eyes.log       # 로그 파일
├── .env                       # 환경변수 (gitignore)
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── Makefile
└── pyproject.toml
```

## Docker 실행

### 전제조건

- Docker Desktop for Mac (Apple Silicon) 설치
- Ollama 별도 실행 필요 (Docker 내에서 RTSP 접근이 제한적일 수 있음)

### 실행

```bash
# Ollama 먼저 실행 (로컬)
ollama pull qwen2-vl:2b
ollama serve

# Docker Compose
make docker-up

# 로그 확인
make docker-logs

# 종료
make docker-down
```

> **참호**: Mac에서 RTSP 스트림 접근을 위해 `network_mode: "host"`를 사용합니다. Ollama는 로컬에서 실행하는 것을 권장합니다.

## 메모리 사용량

| 구성 요소 | 예상 메모리 |
|---|---|
| macOS 시스템 | 2.0GB |
| YOLOv8n (MPS) | 0.3GB |
| Ollama (qwen2-vl:2b Q4) | 1.5GB |
| 프레임 버퍼 | 0.1GB |
| 앱 오버헤드 | 0.3GB |
| **합계** | **~4.2GB** |

여유: 약 3.8GB (8GB 기준)

## 문제 해결

### RTSP 연결 실패

```
ERROR rtsp_open_failed camera_id=cam_01
```

1. 카메라 IP 확인: `ping 192.168.1.100`
2. RTSP URL 직접 테스트:
   ```bash
   ffplay rtsp://admin:password@192.168.1.100:554/stream1
   ```
3. Tapo 앱에서 RTSP 활성화 확인
4. 방화벽 확인: 포트 554 개방

### Ollama 연결 실패

```
ERROR vlm_error error="Connection refused"
```

1. Ollama 실행 확인:
   ```bash
   ollama list
   ollama ps
   ```
2. 모델 다운로드 확인:
   ```bash
   ollama pull qwen2-vl:2b
   ```
3. Ollama 서버 재시작:
   ```bash
   brew services restart ollama
   ```

### 메모리 부족

```
WARNING memory_limit_exceeded_triggering_gc
```

1. `config/settings.yaml`에서 `idle_interval` 증가 (3.0 → 5.0)
2. `max_queue_size` 감소 (3 → 2)
3. 다른 앱 종료
4. VLM 모델 더 작은 것으로 변경:
   ```bash
   ollama pull llava:3b
   # settings.yaml에서 model: "llava:3b"로 변경
   ```

### 텔레그램 알림 안옴

1. 봇 토큰 확인:
   ```bash
   curl https://api.telegram.org/bot<YOUR_TOKEN>/getMe
   ```
2. chat_id 확인:
   ```bash
   curl https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
   ```
3. 봇에게 먼저 `/start` 메시지 전송 필요

### YOLO 모델 다운로드 실패

최초 실행 시 YOLOv8n.pt가 자동 다운로드됩니다. 네트워크 문제 시 수동 다운로드:

```python
from ultralytics import YOLO
YOLO('yolov8n.pt')
```

## 성능 튜닝

### 더 빠르게 (정확도 trade-off)

```yaml
detection:
  confidence: 0.4            # 더 낮은 임계값
  adaptive:
    idle_interval: 2.0       # 더 자주 분석
    active_interval: 0.3
```

### 더 적은 메모리

```yaml
system:
  max_memory_gb: 4.0

rtsp:
  frame:
    target_width: 480
    target_height: 480
    max_queue_size: 2

vlm:
  max_images: 1

storage:
  keyframes_per_event: 1
```

### 더 정확한 분석

```yaml
vlm:
  model: "qwen2-vl:7b"       # 7B 모델 (swap 주의)
  timeout: 60
  max_images: 3

detection:
  model: "yolov8s.pt"        # 더 큰 YOLO 모델
  confidence: 0.6
```

## 로그 확인

```bash
# 실시간 로그
tail -f data/logs/red_eyes.log

# 메모리 상태
grep memory_status data/logs/red_eyes.log | tail -5

# 재연결 이력
grep rtsp_reconnect data/logs/red_eyes.log

# 이벤트 발생
grep event_saved data/logs/red_eyes.log
```

## Makefile 명령어

```bash
make install      # 의존성 설치
make run          # 시스템 실행
make test         # 테스트 실행
make lint         # 린트 체크
make lint-fix     # 린트 자동 수정
make clean        # 이벤트 데이터 정리
make setup        # 전체 초기 설정
```

## 텔레그램 알림 예시

```
📦 RED EYES ALERT

📌 유형: delivery
📍 카메라: 현관
⏰ 시간: 2024-03-15 14:32:18
⏱️ 체류: 45초

📝 분석:
남성이 현관 앞에 접근하여 30초간 대기 후
작은 상자를 바닥에 내려놓고 떠났습니다.

[Keyframe 이미지 1]
[Keyframe 이미지 2]
```

## 라이선스

MIT
