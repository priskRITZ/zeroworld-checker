# -*- coding: utf-8 -*-
"""
제로월드 예약 모니터링 시스템 메인 모듈

09:00 ~ 21:00 동안 5분 간격으로 제로월드 홍대 '층간소음' 예약 페이지를 체크하고
새로 예약 가능해진 슬롯이 있으면 텔레그램으로 알림을 전송
"""

import sys
import signal
import time
import zoneinfo
import asyncio
import threading
from datetime import datetime, timedelta
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
from loguru import logger

from .config import (
    RUN_HOURS, TIMEZONE, CHECK_INTERVAL_MINUTES,
    LOG_FILE, LOG_ROTATION, LOG_RETENTION, LOG_LEVEL,
    DATE_START, DATE_END, THEME_NAME
)
from .fetch import get_slots
from .state import get_state_manager, find_new_available_slots, update_slots
from .notifier import send_notification, send_error_notification, test_telegram_connection, get_bot_handler, test_bot_polling


class ZeroworldChecker:
    """제로월드 예약 모니터링 클래스"""
    
    def __init__(self):
        self.scheduler = BlockingScheduler(timezone=TIMEZONE)
        self.state_manager = get_state_manager()
        self.running = False
        self.check_count = 0
        self.last_success_time = None
        self.error_count = 0
        self.start_time = None  # 모니터링 시작 시간
        
        # 텔레그램 봇 핸들러 설정
        self.bot_handler = get_bot_handler()
        if self.bot_handler:
            self.bot_handler.set_monitor_instance(self)
        
        # 봇 polling용 별도 스레드
        self.bot_thread = None
        self.bot_loop = None
        
        # 로깅 설정
        self._setup_logging()
        
        # 스케줄러 이벤트 리스너 등록
        self.scheduler.add_listener(
            self._job_executed_listener, 
            EVENT_JOB_EXECUTED | EVENT_JOB_ERROR
        )
        
        # 신호 핸들러 등록 (Ctrl+C 처리)
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _setup_logging(self):
        """로깅 설정"""
        # 기본 로거 제거
        logger.remove()
        
        # 콘솔 로거 추가
        logger.add(
            sys.stderr,
            level=LOG_LEVEL,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
        )
        
        # 파일 로거 추가 (클라우드 환경에서는 건너뛰기)
        if LOG_FILE:
            logger.add(
                LOG_FILE,
                level=LOG_LEVEL,
                format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
                rotation=LOG_ROTATION,
                retention=LOG_RETENTION,
                compression="zip"
            )
        else:
            logger.info("클라우드 환경 감지 - 파일 로깅 비활성화")
        
        logger.info("로깅 시스템 초기화 완료")
    
    def _signal_handler(self, signum, frame):
        """시그널 핸들러 (종료 처리)"""
        logger.info(f"종료 신호 받음: {signum}")
        self.stop()
    
    def _job_executed_listener(self, event):
        """스케줄러 작업 실행 이벤트 리스너"""
        if event.exception:
            self.error_count += 1
            logger.error(f"작업 실행 중 오류: {event.exception}")
            
            # 연속 에러가 많으면 알림
            if self.error_count >= 3:
                send_error_notification(f"연속 {self.error_count}회 오류 발생: {event.exception}")
        else:
            self.error_count = 0  # 성공시 에러 카운트 리셋
            self.last_success_time = datetime.now()
    
    def _should_run_now(self) -> bool:
        """현재 실행 시간인지 확인"""
        now = datetime.now()
        current_hour = now.hour
        
        # 운영 시간 체크 (09:00 ~ 20:59)
        if current_hour not in RUN_HOURS:
            logger.debug(f"운영 시간 외: {current_hour}시")
            return False
        
        return True
    
    def check_slots(self):
        """슬롯 체크 및 알림 메인 로직"""
        try:
            self.check_count += 1
            logger.info(f"=== 슬롯 체크 시작 ({self.check_count}회차) ===")
            
            # 운영 시간 체크
            if not self._should_run_now():
                logger.info("운영 시간이 아니므로 체크를 건너뜁니다")
                return
            
            # 1. 현재 슬롯 상태 가져오기
            logger.info(f"'{THEME_NAME}' 슬롯 정보 수집 중...")
            current_slots = get_slots()
            
            if not current_slots:
                logger.warning("슬롯 정보를 가져올 수 없습니다")
                return
            
            logger.info(f"총 {len(current_slots)}개 슬롯 정보 수집 완료")
            
            # 2. 예약 가능한 슬롯 개수 확인
            available_count = len([s for s in current_slots.values() if s == "예약가능"])
            reserved_count = len(current_slots) - available_count
            
            logger.info(f"예약 가능: {available_count}개, 매진: {reserved_count}개")
            
            # 3. 현재 예약 가능한 모든 슬롯 찾기 (항상 알림)
            available_slots = [slot for slot, status in current_slots.items() if status == "예약가능"]
            
            # 4. 예약 가능한 슬롯이 있으면 알림 전송
            if available_slots:
                logger.info(f"🎉 예약 가능한 슬롯 {len(available_slots)}개 발견!")
                
                for slot in available_slots:
                    logger.info(f"  - {slot}")
                
                # 텔레그램 알림 전송 (매번 전송)
                if send_notification(available_slots):
                    logger.info("✅ 텔레그램 알림 전송 성공")
                else:
                    logger.error("❌ 텔레그램 알림 전송 실패")
            else:
                logger.info("현재 예약 가능한 슬롯이 없습니다")
            
            # 5. 현재 상태 저장
            if update_slots(current_slots):
                logger.debug("상태 저장 완료")
            else:
                logger.warning("상태 저장 실패")
            
            # 6. 통계 정보 출력
            stats = self.state_manager.get_stats()
            logger.info(f"📊 통계 - 전체: {stats['total_slots']}개, 예약가능: {stats['available_slots']}개")
            
            logger.info("=== 슬롯 체크 완료 ===")
            
        except KeyboardInterrupt:
            logger.info("사용자에 의해 중단됨")
            raise
        except Exception as e:
            logger.error(f"슬롯 체크 중 오류: {e}")
            # 중요한 오류는 텔레그램으로도 알림
            if "network" in str(e).lower() or "connection" in str(e).lower():
                send_error_notification(f"네트워크 오류: {e}")
    
    def send_status_message(self):
        """정각마다 모니터링 상태 메시지 전송"""
        try:
            if not self.start_time:
                logger.warning("시작 시간이 설정되지 않아 상태 메시지를 보낼 수 없습니다")
                return
            
            # 런타임 계산
            now = datetime.now()
            runtime = now - self.start_time
            hours = int(runtime.total_seconds() // 3600)
            minutes = int((runtime.total_seconds() % 3600) // 60)
            
            # 상태 메시지 생성
            if hours > 0:
                runtime_str = f"{hours}시간 {minutes}분"
            else:
                runtime_str = f"{minutes}분"
            
            status_msg = (
                f"🤖 모니터링 정상 작동중\n"
                f"⏰ 런타임: {runtime_str}\n"
                f"📊 총 체크 횟수: {self.check_count}\n"
                f"✅ 마지막 성공: {self.last_success_time.strftime('%H:%M:%S') if self.last_success_time else '없음'}\n"
                f"❌ 에러 횟수: {self.error_count}"
            )
            
            # 텔레그램 알림 전송 (상태 메시지용 함수 사용)
            from .notifier import send_status_notification
            if send_status_notification(status_msg):
                logger.info("✅ 상태 메시지 전송 성공")
            else:
                logger.warning("❌ 상태 메시지 전송 실패")
                
        except Exception as e:
            logger.error(f"상태 메시지 전송 중 오류: {e}")
    
    def _start_bot_polling(self):
        """별도 스레드에서 텔레그램 봇 polling 시작"""
        if not self.bot_handler or not self.bot_handler.application:
            logger.warning("텔레그램 봇이 설정되지 않아 polling을 시작할 수 없습니다")
            return
        
        def run_bot():
            """봇 polling 실행 함수"""
            try:
                # 새로운 이벤트 루프 생성
                self.bot_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self.bot_loop)
                
                # 봇 polling 시작
                self.bot_loop.run_until_complete(self.bot_handler.start_polling())
                
            except Exception as e:
                logger.error(f"봇 polling 스레드 오류: {e}")
        
        # 별도 스레드에서 봇 실행
        self.bot_thread = threading.Thread(target=run_bot, daemon=True)
        self.bot_thread.start()
        logger.info("📱 텔레그램 봇 polling 시작됨 (별도 스레드)")
    
    def _stop_bot_polling(self):
        """텔레그램 봇 polling 중지"""
        if self.bot_handler and self.bot_loop:
            try:
                # 비동기 함수를 동기적으로 실행
                future = asyncio.run_coroutine_threadsafe(
                    self.bot_handler.stop_polling(), 
                    self.bot_loop
                )
                future.result(timeout=5)  # 5초 타임아웃
                logger.info("📱 텔레그램 봇 polling 중지됨")
                
            except Exception as e:
                logger.error(f"봇 polling 중지 오류: {e}")
        
        if self.bot_thread and self.bot_thread.is_alive():
            try:
                self.bot_thread.join(timeout=5)
            except Exception as e:
                logger.error(f"봇 스레드 종료 오류: {e}")
    
    def test_system(self) -> bool:
        """시스템 전체 테스트"""
        logger.info("🔧 시스템 테스트 시작")
        
        try:
            # 1. 텔레그램 연결 테스트
            logger.info("1. 텔레그램 연결 테스트...")
            if not test_telegram_connection():
                logger.error("❌ 텔레그램 연결 실패")
                return False
            logger.info("✅ 텔레그램 연결 성공")
            
            # 2. API 연결 테스트
            logger.info("2. 제로월드 API 연결 테스트...")
            test_slots = get_slots()
            if test_slots is None:
                logger.error("❌ API 연결 실패: 웹사이트와 통신할 수 없거나 페이지 구조가 변경되었을 수 있습니다.")
                return False
            logger.info(f"✅ API 연결 성공 ({len(test_slots)}개 슬롯 발견)")
            
            # 3. 상태 관리 테스트
            logger.info("3. 상태 관리 테스트...")
            if not update_slots(test_slots):
                logger.error("❌ 상태 저장 실패")
                return False
            logger.info("✅ 상태 관리 성공")
            
            logger.info("🎉 모든 시스템 테스트 통과!")
            return True
            
        except Exception as e:
            logger.error(f"❌ 시스템 테스트 실패: {e}")
            return False
    
    def start(self):
        """모니터링 시작"""
        self.start_time = datetime.now()  # 시작 시간 기록
        
        logger.info("🚀 제로월드 예약 모니터링 시스템 시작")
        logger.info(f"📅 모니터링 기간: {DATE_START} ~ {DATE_END}")
        logger.info(f"🎯 대상 테마: {THEME_NAME}")
        logger.info(f"⏰ 운영 시간: 24시간 무제한 모니터링")
        logger.info(f"🔄 체크 간격: {CHECK_INTERVAL_MINUTES}분")
        logger.info(f"📱 정각마다 상태 메시지 전송")
        logger.info(f"🤖 텔레그램 봇 명령어: /status (현재 상태), /help (도움말)")
        
        # 시스템 테스트
        if not self.test_system():
            logger.error("시스템 테스트 실패로 모니터링을 시작할 수 없습니다")
            return
        
        # 즉시 한 번 실행
        logger.info("초기 슬롯 체크 실행...")
        try:
            self.check_slots()
        except Exception as e:
            logger.warning(f"초기 체크 실패: {e}")
        
        # 스케줄러에 작업 추가
        self.scheduler.add_job(
            func=self.check_slots,
            trigger='interval',
            minutes=CHECK_INTERVAL_MINUTES,
            id='slot_checker',
            name='제로월드 슬롯 체크',
            misfire_grace_time=30,  # 30초까지 지연 허용
            max_instances=1  # 동시 실행 방지
        )
        
        # 정각마다 상태 메시지 전송 작업 추가
        self.scheduler.add_job(
            func=self.send_status_message,
            trigger='cron',
            minute=0,  # 매 정각(00분)
            id='status_messenger',
            name='모니터링 상태 메시지',
            misfire_grace_time=60,  # 1분까지 지연 허용
            max_instances=1
        )
        
        # 텔레그램 봇 polling 시작
        self._start_bot_polling()
        
        # 스케줄러 시작
        try:
            self.running = True
            logger.info("⚡ 스케줄러 시작됨")
            logger.info("모니터링 중... (Ctrl+C로 중지)")
            
            self.scheduler.start()
            
        except KeyboardInterrupt:
            logger.info("사용자에 의해 중단됨")
        except Exception as e:
            logger.error(f"스케줄러 오류: {e}")
        finally:
            self.stop()
    
    def stop(self):
        """모니터링 중지"""
        if self.running:
            logger.info("🛑 모니터링 중지 중...")
            self.running = False
            
            # 텔레그램 봇 polling 중지
            self._stop_bot_polling()
            
            if self.scheduler.running:
                self.scheduler.shutdown(wait=False)
            
            # 최종 통계
            logger.info(f"📊 최종 통계:")
            logger.info(f"  - 총 체크 횟수: {self.check_count}")
            logger.info(f"  - 마지막 성공: {self.last_success_time}")
            logger.info(f"  - 에러 횟수: {self.error_count}")
            
            logger.info("✅ 모니터링 시스템 종료 완료")
    
    def run_once(self):
        """한 번만 실행 (테스트용)"""
        logger.info("🔍 단일 실행 모드")
        
        if not self.test_system():
            logger.error("시스템 테스트 실패")
            return False
        
        try:
            self.check_slots()
            return True
        except Exception as e:
            logger.error(f"실행 실패: {e}")
            return False


def main():
    """메인 함수"""
    import argparse
    
    parser = argparse.ArgumentParser(description='제로월드 예약 모니터링 시스템')
    parser.add_argument('--test', action='store_true', help='시스템 테스트만 실행')
    parser.add_argument('--once', action='store_true', help='한 번만 체크하고 종료')
    parser.add_argument('--config-test', action='store_true', help='설정 테스트')
    parser.add_argument('--bot-test', action='store_true', help='텔레그램 봇 polling 테스트')
    parser.add_argument('--railway-test', action='store_true', help='Railway API 설정 테스트')
    
    args = parser.parse_args()
    
    checker = ZeroworldChecker()
    
    if args.config_test:
        # 설정 확인
        logger.info("=== 설정 확인 ===")
        from .config import BOT_TOKEN, CHAT_ID
        print(f"봇 토큰: {'설정됨' if BOT_TOKEN != 'YOUR_BOT_TOKEN_HERE' else '❌ 미설정'}")
        print(f"채팅 ID: {'설정됨' if CHAT_ID != 0 else '❌ 미설정'}")
        print(f"모니터링 기간: {DATE_START} ~ {DATE_END}")
        print(f"대상 테마: {THEME_NAME}")
        print(f"운영 시간: {RUN_HOURS.start:02d}:00 ~ {RUN_HOURS.stop-1:02d}:59")
        
    elif args.bot_test:
        # 텔레그램 봇 polling 테스트
        if test_bot_polling():
            logger.info("🎉 봇 polling 테스트 완료!")
            logger.info("💡 이제 텔레그램에서 /test 명령어를 입력해보세요")
            sys.exit(0)
        else:
            logger.error("❌ 봇 polling 테스트 실패!")
            sys.exit(1)
    
    elif args.railway_test:
        # Railway API 설정 테스트
        logger.info("=== Railway API 설정 테스트 ===")
        from .railway_api import test_railway_settings
        if test_railway_settings():
            logger.info("🎉 Railway API 설정 완료!")
            sys.exit(0)
        else:
            logger.error("❌ Railway API 설정 미완료!")
            sys.exit(1)
            
    elif args.test:
        # 시스템 테스트만
        if checker.test_system():
            logger.info("🎉 모든 테스트 통과!")
            sys.exit(0)
        else:
            logger.error("❌ 테스트 실패!")
            sys.exit(1)
            
    elif args.once:
        # 한 번만 실행
        if checker.run_once():
            logger.info("✅ 실행 완료")
            sys.exit(0)
        else:
            logger.error("❌ 실행 실패")
            sys.exit(1)
    else:
        # 일반 모니터링 모드
        checker.start()


if __name__ == "__main__":
    main() 