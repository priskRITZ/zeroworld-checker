# -*- coding: utf-8 -*-
"""
제로월드 예약 모니터링 시스템 설정 파일
"""

from pathlib import Path
import os
from datetime import datetime, timedelta

# 텔레그램 봇 설정 (환경변수에서 읽기)
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
CHAT_ID_STR = os.getenv("TELEGRAM_CHAT_ID", "0")
try:
    CHAT_ID = int(CHAT_ID_STR)
except ValueError:
    CHAT_ID = 0  # 기본값 (설정 필요함을 알림)

# 모니터링 대상 설정
# main 브랜치: "층간소음", test 브랜치: "사랑하는감?"
BRANCH_THEME_MAPPING = {
    "main": "층간소음",
    "master": "층간소음",
    "test": "사랑하는감?"
}

# Railway 환경변수에서 현재 브랜치 이름 가져오기 (없을 경우 "main"을 기본값으로)
current_branch = os.getenv("RAILWAY_GIT_BRANCH", "main")

# 현재 브랜치에 맞춰 테마 이름 동적 설정
THEME_NAME = BRANCH_THEME_MAPPING.get(current_branch, "층간소음")

# Date range (starts today and extends LOOKAHEAD_DAYS days)
today = datetime.now().date()
DATE_START = today.strftime("%Y-%m-%d")  # 현재 날짜부터
# LOOKAHEAD_DAYS 환경변수로 조절 가능한 기본 60일 탐색 범위
LOOKAHEAD_DAYS = int(os.getenv("LOOKAHEAD_DAYS", "60"))
MAX_RESERVATION_DATE = datetime(2025, 11, 16).date()
calculated_end = today + timedelta(days=max(LOOKAHEAD_DAYS, 7))
DATE_END = min(calculated_end, MAX_RESERVATION_DATE).strftime("%Y-%m-%d")

# 시간 설정
TIMEZONE = "Asia/Seoul"
RUN_HOURS = range(0, 24)  # 24시간 무제한 모니터링
CHECK_INTERVAL_MINUTES = 1

# Railway 환경에서 한국 시간대 강제 설정
import os
if os.getenv("RAILWAY_ENVIRONMENT_NAME"):
    os.environ['TZ'] = 'Asia/Seoul'
    import time
    time.tzset() if hasattr(time, 'tzset') else None

# 파일 경로
# 클라우드 환경 감지
IS_CLOUD = os.getenv("RAILWAY_ENVIRONMENT_NAME") is not None or os.getenv("RENDER") is not None

if IS_CLOUD:
    # 클라우드 환경에서는 로그를 stdout으로 출력
    LOG_FILE = None  # stdout 사용
    # 상태 파일도 메모리 기반으로 변경 (옵션)
    STATE_FILE = Path("/tmp/state.json") if os.path.exists("/tmp") else Path("state.json")
else:
    # 로컬 환경
    STATE_FILE = Path("state.json")
    LOG_FILE = "checker.log"

# HTTP 요청 설정
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
REQUEST_TIMEOUT = 10

# 제로월드 URL 설정
BASE_URL = "https://zerohongdae.com"
RESERVATION_URL = f"{BASE_URL}/reservation"

# 로그 설정
LOG_LEVEL = "DEBUG"  # 디버깅을 위해 DEBUG 레벨로 변경
LOG_ROTATION = "1 MB"
LOG_RETENTION = "5 days"

# 알림 설정
MAX_NOTIFICATION_SLOTS = 10  # 한 번에 최대 알림 개수
NOTIFICATION_COOLDOWN = 300  # 연속 알림 방지 쿨타임 (초) 
