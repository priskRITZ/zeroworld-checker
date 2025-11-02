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

# --- 테마 설정 (동적) ---
BRANCH_THEME_MAPPING = {
    "main": "층간소음",
    "master": "층간소음",
    "test": "사랑하는감?"
}

# Railway 환경변수에서 현재 브랜치 이름 가져오기 (없을 경우 "main"을 기본값으로)
current_branch = os.getenv("RAILWAY_GIT_BRANCH", "main")

# 현재 브랜치에 맞춰 테마 이름 동적 설정
THEME_NAME = BRANCH_THEME_MAPPING.get(current_branch, "층간소음")
# ---

# --- 날짜 설정 (고정) ---
today = datetime.now().date()
DATE_START = today.strftime("%Y-%m-%d")  # 현재 날짜부터

# 사용자가 요청한 대로, 모니터링 종료 날짜를 2025년 11월 17일로 고정합니다.
DATE_END = "2025-11-17"
# ---

# 시간 설정
TIMEZONE = "Asia/Seoul"
RUN_HOURS = range(0, 24)  # 24시간 무제한 모니터링
CHECK_INTERVAL_MINUTES = 1

# Railway 환경에서 한국 시간대 강제 설정
if os.getenv("RAILWAY_ENVIRONMENT_NAME"):
    os.environ['TZ'] = 'Asia/Seoul'
    import time
    if hasattr(time, 'tzset'):
        time.tzset()

# 파일 경로
IS_CLOUD = os.getenv("RAILWAY_ENVIRONMENT_NAME") is not None or os.getenv("RENDER") is not None

if IS_CLOUD:
    LOG_FILE = None
    STATE_FILE = Path("/tmp/state.json") if os.path.exists("/tmp") else Path("state.json")
else:
    STATE_FILE = Path("state.json")
    LOG_FILE = "checker.log"

# HTTP 요청 설정
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
REQUEST_TIMEOUT = 10

# 제로월드 URL 설정
BASE_URL = "https://zerohongdae.com"
RESERVATION_URL = f"{BASE_URL}/reservation"

# 로그 설정
LOG_LEVEL = "DEBUG"
LOG_ROTATION = "1 MB"
LOG_RETENTION = "5 days"

# 알림 설정
MAX_NOTIFICATION_SLOTS = 10
NOTIFICATION_COOLDOWN = 300