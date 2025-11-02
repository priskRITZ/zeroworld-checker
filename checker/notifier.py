# -*- coding: utf-8 -*-
"""
텔레그램 알림 전송 모듈

새로 예약 가능해진 슬롯 정보를 텔레그램으로 전송
"""

import asyncio
import time
from typing import Dict, List, Optional
from datetime import datetime
from loguru import logger

try:
    from telegram import Bot, Update
    from telegram.ext import Application, CommandHandler, ContextTypes
    from telegram.error import TelegramError, RetryAfter, NetworkError
    TELEGRAM_AVAILABLE = True
except ImportError:
    logger.warning("python-telegram-bot가 설치되지 않았습니다. 텔레그램 알림이 비활성화됩니다.")
    TELEGRAM_AVAILABLE = False

from .config import BOT_TOKEN, CHAT_ID, MAX_NOTIFICATION_SLOTS, NOTIFICATION_COOLDOWN


class TelegramNotifier:
    """텔레그램 알림 전송 클래스"""
    
    def __init__(self, bot_token: str = BOT_TOKEN, chat_id: int = CHAT_ID):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.bot = None
        self.last_notification_time = 0
        self._initialize_bot()
    
    def _initialize_bot(self):
        """봇 초기화"""
        if not TELEGRAM_AVAILABLE:
            logger.error("python-telegram-bot가 설치되지 않았습니다!")
            return
            
        try:
            if self.bot_token == "YOUR_BOT_TOKEN_HERE":
                logger.error("텔레그램 봇 토큰이 설정되지 않았습니다!")
                logger.info("환경변수 TELEGRAM_BOT_TOKEN을 설정하거나 config.py를 수정하세요.")
                return
            
            if self.chat_id == 0:
                logger.error("텔레그램 채팅 ID가 설정되지 않았습니다!")
                logger.info("환경변수 TELEGRAM_CHAT_ID를 설정하거나 config.py를 수정하세요.")
                return
            
            # Bot 객체에 timeout 설정
            from telegram.request import HTTPXRequest
            request = HTTPXRequest(
                read_timeout=10,
                write_timeout=10,
                connect_timeout=10
            )
            self.bot = Bot(token=self.bot_token, request=request)
            logger.info("텔레그램 봇 초기화 완료")
            
        except Exception as e:
            logger.error(f"텔레그램 봇 초기화 실패: {e}")
            self.bot = None
    
    async def test_connection(self) -> bool:
        """텔레그램 봇 연결 테스트"""
        if not self.bot:
            logger.error("텔레그램 봇이 초기화되지 않았습니다")
            return False
        
        try:
            # 봇 정보 가져오기
            bot_info = await self.bot.get_me()
            logger.info(f"봇 연결 성공: @{bot_info.username} ({bot_info.first_name})")
            
            # 테스트 메시지 전송
            test_message = "🔧 제로월드 예약 모니터링 시스템\n연결 테스트가 성공했습니다!"
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=test_message,
                parse_mode='HTML'
            )
            logger.info(f"테스트 메시지 전송 완료 (채팅 ID: {self.chat_id})")
            return True
            
        except TelegramError as e:
            if "chat not found" in str(e).lower():
                logger.error(f"채팅 ID {self.chat_id}를 찾을 수 없습니다. 올바른 채팅 ID인지 확인하세요.")
            elif "unauthorized" in str(e).lower():
                logger.error(f"봇 토큰이 잘못되었거나 만료되었습니다: {e}")
            else:
                logger.error(f"텔레그램 API 오류: {e}")
            return False
        except Exception as e:
            logger.error(f"연결 테스트 중 예상치 못한 오류: {e}")
            return False
    
    def _should_send_notification(self) -> bool:
        """알림 전송 가능 여부 확인 (쿨타임 체크)"""
        current_time = time.time()
        if current_time - self.last_notification_time < NOTIFICATION_COOLDOWN:
            remaining = NOTIFICATION_COOLDOWN - (current_time - self.last_notification_time)
            logger.info(f"알림 쿨타임 중입니다. {remaining:.0f}초 후 재시도 가능")
            return False
        return True
    
    def _format_slots_message(self, new_slots: List[str]) -> str:
        """슬롯 정보를 메시지 형식으로 포맷팅"""
        if not new_slots:
            return ""
        
        # 슬롯 개수 제한
        slots_to_show = new_slots[:MAX_NOTIFICATION_SLOTS]
        
        # 각 슬롯별로 개별 라인 생성
        message_lines = []
        
        for slot in sorted(slots_to_show):
            try:
                date_part, time_part = slot.split(' ', 1)
                
                # 날짜 포맷팅: 2025-07-30 -> 7월30일
                date_obj = datetime.strptime(date_part, '%Y-%m-%d')
                month = date_obj.month
                day = date_obj.day
                date_korean = f"{month}월{day}일"
                
                # 시간 포맷팅: HH:MM:SS -> HH:MM
                time_formatted = time_part[:5] if len(time_part) >= 5 else time_part
                
                # 메시지 라인 생성: "예약가능확인! {테마이름} 7월30일, 14:00"
                from .config import THEME_NAME
                line = f"예약가능확인! {THEME_NAME} {date_korean}, {time_formatted}"
                message_lines.append(line)
                
            except (ValueError, IndexError) as e:
                # 파싱 오류시 원본 그대로 사용
                message_lines.append(f"예약가능확인! 층간소음 {slot}")
        
        # 더 많은 슬롯이 있는 경우 안내 추가
        if len(new_slots) > MAX_NOTIFICATION_SLOTS:
            message_lines.append(f"... 외 {len(new_slots) - MAX_NOTIFICATION_SLOTS}개 슬롯 더 있음")
        
        # 예약 링크 추가
        message_lines.append("https://zerohongdae.com/reservation")
        
        # 줄바꿈으로 연결하여 반환
        return "\n".join(message_lines)
    
    async def send_notification(self, new_slots: List[str]) -> bool:
        """새로 예약 가능해진 슬롯 알림 전송"""
        if not self.bot:
            logger.error("텔레그램 봇이 초기화되지 않았습니다")
            return False
        
        if not new_slots:
            logger.info("알림할 새로운 슬롯이 없습니다")
            return True
        
        if not self._should_send_notification():
            return False
        
        try:
            message = self._format_slots_message(new_slots)
            
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode='HTML',
                disable_web_page_preview=True
            )
            
            self.last_notification_time = time.time()
            logger.info(f"알림 전송 완료: {len(new_slots)}개 새로운 슬롯")
            return True
            
        except RetryAfter as e:
            logger.warning(f"텔레그램 속도 제한, {e.retry_after}초 후 재시도")
            return False
        except NetworkError as e:
            logger.error(f"네트워크 오류: {e}")
            return False
        except TelegramError as e:
            logger.error(f"텔레그램 오류: {e}")
            return False
        except Exception as e:
            logger.error(f"알림 전송 중 예상치 못한 오류: {e}")
            return False
    
    async def send_error_notification(self, error_message: str) -> bool:
        """에러 알림 전송"""
        if not self.bot:
            return False
        
        try:
            message = f"⚠️ <b>제로월드 모니터링 오류</b>\n\n{error_message}\n\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode='HTML'
            )
            
            logger.info("에러 알림 전송 완료")
            return True
            
        except Exception as e:
            logger.error(f"에러 알림 전송 실패: {e}")
            return False
    
    async def _send_status_message_async(self, status_message: str) -> bool:
        """상태 메시지 전송 (비동기)"""
        if not self.bot:
            return False
        
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=status_message,
                parse_mode='HTML'
            )
            
            logger.info("상태 메시지 전송 완료")
            return True
            
        except Exception as e:
            logger.error(f"상태 메시지 전송 실패: {e}")
            return False


class TelegramBotHandler:
    """텔레그램 봇 명령어 처리 클래스"""
    
    def __init__(self, monitor_instance=None):
        self.monitor_instance = monitor_instance
        self.application = None
        
        if TELEGRAM_AVAILABLE and BOT_TOKEN != "YOUR_BOT_TOKEN_HERE":
            # Bot 객체에 timeout 설정
            from telegram.request import HTTPXRequest
            request = HTTPXRequest(
                read_timeout=10,
                write_timeout=10,
                connect_timeout=10
            )
            self.application = Application.builder().token(BOT_TOKEN).request(request).build()
            self._setup_handlers()
    
    def _setup_handlers(self):
        """명령어 핸들러 설정"""
        if not self.application:
            return
        
        # 명령어 핸들러를 먼저 등록 (우선순위)
        # /status 명령어 핸들러
        self.application.add_handler(CommandHandler("status", self.handle_status_command))
        
        # /help 명령어 핸들러
        self.application.add_handler(CommandHandler("help", self.handle_help_command))
        
        # /start 명령어 핸들러
        self.application.add_handler(CommandHandler("start", self.handle_start_command))
        
        # /test 명령어 핸들러 (봇 테스트용)
        self.application.add_handler(CommandHandler("test", self.handle_test_command))
        
        # /branch 명령어 핸들러 (브랜치 전환용)
        self.application.add_handler(CommandHandler("branch", self.handle_branch_command))
        
        # 모든 메시지 핸들러 (디버깅용 - 마지막에 등록)
        from telegram.ext import MessageHandler, filters
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_all_messages))
        
        logger.info("🎯 텔레그램 봇 핸들러 등록 완료: /status, /help, /start, /test, /branch")
    
    async def handle_status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /status 명령어 처리 - 현재 모니터링 상태 정보 전송
        """
        try:
            if not self.monitor_instance:
                await update.message.reply_text("❌ 모니터링 인스턴스가 설정되지 않았습니다.")
                return
            
            # 현재 시간
            now = datetime.now()
            
            # 런타임 계산
            if self.monitor_instance.start_time:
                runtime = now - self.monitor_instance.start_time
                hours = int(runtime.total_seconds() // 3600)
                minutes = int((runtime.total_seconds() % 3600) // 60)
                runtime_str = f"{hours}시간 {minutes}분" if hours > 0 else f"{minutes}분"
            else:
                runtime_str = "시작 시간 미설정"
            
            # 상태 메시지 생성
            status_msg = (
                f"🤖 <b>제로월드 모니터링 상태</b>\n\n"
                f"⏰ <b>런타임:</b> {runtime_str}\n"
                f"📊 <b>총 체크 횟수:</b> {self.monitor_instance.check_count}\n"
                f"✅ <b>마지막 성공:</b> {self.monitor_instance.last_success_time.strftime('%H:%M:%S') if self.monitor_instance.last_success_time else '없음'}\n"
                f"❌ <b>에러 횟수:</b> {self.monitor_instance.error_count}\n"
                f"🔄 <b>모니터링 상태:</b> {'실행 중' if self.monitor_instance.running else '중지됨'}\n\n"
                f"⏰ <b>현재 시간:</b> {now.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            
            await update.message.reply_text(status_msg, parse_mode='HTML')
            logger.info(f"사용자 {update.effective_user.first_name}이 /status 명령어 실행")
            
        except Exception as e:
            logger.error(f"/status 명령어 처리 중 오류: {e}")
            await update.message.reply_text("❌ 상태 정보를 가져오는 중 오류가 발생했습니다.")
    
    async def handle_help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /help 명령어 처리 - 사용 가능한 명령어 안내
        """
        help_msg = (
            f"🤖 <b>제로월드 모니터링 봇 명령어</b>\n\n"
            f"📊 <b>/status</b> - 현재 모니터링 상태 확인\n"
            f"🌿 <b>/branch</b> - Railway 브랜치 전환 및 배포\n"
            f"   • <code>/branch main</code> - 메인 브랜치 (층간소음 테마)\n"
            f"   • <code>/branch test</code> - 테스트 브랜치 (사랑하는감? 테마)\n"
            f"   • ⏱️ 브랜치 전환 후 약 2-3분 소요\n"
            f"   • 🎯 테스트 브랜치는 예약 슬롯이 많아 테스트 용이\n"
            f"🧪 <b>/test</b> - 봇 연결 테스트\n"
            f"❓ <b>/help</b> - 이 도움말 보기\n"
            f"🚀 <b>/start</b> - 봇 시작 인사\n\n"
            f"💡 <b>자동 기능:</b>\n"
            f"• 예약 가능한 슬롯 발견 시 즉시 알림\n"
            f"• 매 정각 상태 메시지 전송\n"
            f"• 오류 발생 시 자동 알림\n\n"
            f"⚠️ <b>주의사항:</b>\n"
            f"• 브랜치 전환은 새로운 배포를 시작합니다\n"
            f"• 전환 중에는 잠시 서비스가 중단될 수 있습니다"
        )
        
        await update.message.reply_text(help_msg, parse_mode='HTML')
        logger.info(f"사용자 {update.effective_user.first_name}이 /help 명령어 실행")
    
    async def handle_start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /start 명령어 처리 - 환영 메시지
        """
        welcome_msg = (
            f"🎉 <b>제로월드 예약 모니터링 봇에 오신 것을 환영합니다!</b>\n\n"
            f"🎯 <b>현재 모니터링 중:</b> 층간소음 테마\n"
            f"⏰ <b>운영 시간:</b> 24시간 무제한\n"
            f"🔄 <b>체크 간격:</b> 1분마다\n\n"
            f"📱 사용 가능한 명령어를 보려면 /help를 입력하세요."
        )
        
        await update.message.reply_text(welcome_msg, parse_mode='HTML')
        logger.info(f"사용자 {update.effective_user.first_name}이 /start 명령어 실행")
    
    async def handle_test_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /test 명령어 처리 - 봇 연결 테스트
        """
        test_msg = (
            f"✅ <b>봇 테스트 성공!</b>\n\n"
            f"🤖 봇이 정상적으로 작동하고 있습니다.\n"
            f"👤 사용자: {update.effective_user.first_name}\n"
            f"💬 채팅 ID: {update.effective_chat.id}\n"
            f"⏰ 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"🎯 모든 명령어가 정상 작동합니다!"
        )
        
        await update.message.reply_text(test_msg, parse_mode='HTML')
        logger.info(f"사용자 {update.effective_user.first_name}이 /test 명령어 실행 - 봇 정상 작동")
    
    async def handle_branch_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /branch 명령어 처리 - Railway 브랜치 수동 변경 안내
        사용법: /branch main | /branch test
        """
        try:
            user_name = update.effective_user.first_name

            # 인자 확인
            if not context.args:
                help_msg = (
                    f"🌿 <b>브랜치 변경 안내</b>\n\n"
                    f"📖 <b>사용법:</b>\n"
                    f"• <code>/branch main</code> - 메인 브랜치 (층간소음 테마)\n"
                    f"• <code>/branch test</code> - 테스트 브랜치 (사랑하는감? 테마)"
                )
                await update.message.reply_text(help_msg, parse_mode='HTML')
                return

            branch_name = context.args[0].lower()

            # 지원하는 브랜치 확인
            if branch_name not in ["main", "test"]:
                error_msg = (
                    f"❌ <b>지원하지 않는 브랜치입니다</b>\n\n"
                    f"지원하는 브랜치:\n"
                    f"• <code>main</code> - 층간소음 테마\n"
                    f"• <code>test</code> - 사랑하는감? 테마"
                )
                await update.message.reply_text(error_msg, parse_mode='HTML')
                return

            # Railway 프로젝트/서비스 ID 가져오기
            import os
            project_id = os.getenv("RAILWAY_PROJECT_ID")
            service_id = os.getenv("RAILWAY_SERVICE_ID")

            settings_url = "https://railway.app"
            if project_id and service_id:
                settings_url = f"https://railway.app/project/{project_id}/service/{service_id}?view=settings"

            # 안내 메시지 생성
            manual_change_msg = (
                f"🌿 <b>브랜치 수동 변경 안내</b>\n\n"
                f"현재 자동 브랜치 변경은 지원되지 않습니다.\n"
                f"대신 아래 링크에서 직접 브랜치를 변경해주세요.\n\n"
                f"<b>요청 브랜치:</b> {branch_name}\n"
                f"<b>변경될 테마:</b> {'층간소음' if branch_name == 'main' else '사랑하는감?'}\n\n"
                f"<a href='{settings_url}'>🔗 <b>Railway 서비스 설정으로 이동</b></a>\n\n"
                f"페이지 접속 후 'Service Source'에서 브랜치를 변경하고 'Deploy' 버튼을 누르면 적용됩니다."
            )

            await update.message.reply_text(manual_change_msg, parse_mode='HTML', disable_web_page_preview=True)
            logger.info(f"사용자 {user_name}에게 '{branch_name}' 브랜치 수동 변경을 안내했습니다.")

        except Exception as e:
            logger.error(f"/branch 명령어 처리 중 오류: {e}")
            await update.message.reply_text("❌ 명령어 처리 중 오류가 발생했습니다.")
    
    async def handle_all_messages(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        모든 메시지 처리 (디버깅용) - 봇이 메시지를 받는지 확인
        """
        try:
            user = update.effective_user
            message_text = update.message.text if update.message and update.message.text else "알 수 없는 메시지"
            
            logger.info(f"📨 메시지 수신: 사용자={user.first_name}, 내용='{message_text}'")
            
            # 명령어가 아닌 일반 메시지인 경우에만 응답
            if not message_text.startswith('/'):
                response = (
                    f"👋 안녕하세요! 제로월드 모니터링 봇입니다.\n\n"
                    f"📱 사용 가능한 명령어:\n"
                    f"• /status - 모니터링 상태 확인\n"
                    f"• /help - 도움말\n"
                    f"• /test - 봇 테스트\n"
                    f"• /start - 시작 메시지"
                )
                await update.message.reply_text(response)
                
        except Exception as e:
            logger.error(f"메시지 처리 중 오류: {e}")
    
    def set_monitor_instance(self, monitor_instance):
        """모니터링 인스턴스 설정"""
        self.monitor_instance = monitor_instance
    
    async def start_polling(self):
        """봇 polling 시작 (지속적으로 실행)"""
        if not self.application:
            logger.error("텔레그램 애플리케이션이 초기화되지 않았습니다")
            return
        
        try:
            logger.info("텔레그램 봇 polling 시작...")
            
            # 봇 정보 확인
            bot_info = await self.application.bot.get_me()
            logger.info(f"봇 연결 성공: @{bot_info.username} ({bot_info.first_name})")
            
            # 애플리케이션 초기화 및 시작
            await self.application.initialize()
            await self.application.start()
            
            logger.info("🤖 텔레그램 봇이 명령어를 기다리고 있습니다...")
            logger.info("사용 가능한 명령어: /status, /help, /start")
            
            # polling 시작 (지속적으로 실행)
            await self.application.updater.start_polling(
                poll_interval=1.0,  # 1초마다 업데이트 확인
                bootstrap_retries=-1,  # 무제한 재시도
                allowed_updates=None  # 모든 업데이트 허용
            )
            
            # polling이 시작된 후 대기 (이것이 중요!)
            logger.info("📱 봇 polling 활성화됨 - 명령어 수신 대기 중...")
            
            # 이벤트 루프가 계속 실행되도록 대기
            while True:
                await asyncio.sleep(1)
            
        except Exception as e:
            logger.error(f"봇 polling 시작 실패: {e}")
            logger.error(f"오류 세부사항: {type(e).__name__}: {str(e)}")
    
    async def stop_polling(self):
        """봇 polling 중지"""
        if not self.application:
            return
        
        try:
            logger.info("텔레그램 봇 polling 중지...")
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
            
        except Exception as e:
            logger.error(f"봇 polling 중지 실패: {e}")


# 전역 봇 핸들러 인스턴스
_bot_handler = None

def get_bot_handler() -> Optional[TelegramBotHandler]:
    """봇 핸들러 인스턴스 반환"""
    global _bot_handler
    if _bot_handler is None:
        _bot_handler = TelegramBotHandler()
    return _bot_handler


# 동기 함수들 (기존 호환성 유지)
def send_notification(new_slots: List[str]) -> bool:
    """동기 알림 전송 함수"""
    notifier = TelegramNotifier()
    return asyncio.run(notifier.send_notification(new_slots))


def send_error_notification(error_message: str) -> bool:
    """동기 에러 알림 전송 함수"""
    notifier = TelegramNotifier()
    return asyncio.run(notifier.send_error_notification(error_message))


def test_telegram_connection() -> bool:
    """동기 텔레그램 연결 테스트 함수"""
    notifier = TelegramNotifier()
    return asyncio.run(notifier.test_connection())


def test_bot_polling() -> bool:
    """텔레그램 봇 polling 테스트 함수"""
    try:
        logger.info("🧪 텔레그램 봇 polling 테스트 시작")
        
        bot_handler = get_bot_handler()
        if not bot_handler:
            logger.error("❌ 봇 핸들러를 생성할 수 없습니다")
            return False
        
        if not bot_handler.application:
            logger.error("❌ 텔레그램 애플리케이션이 초기화되지 않았습니다")
            logger.info("💡 BOT_TOKEN과 CHAT_ID가 올바르게 설정되었는지 확인하세요")
            return False
        
        logger.info("✅ 봇 핸들러 초기화 성공")
        logger.info("📱 이제 텔레그램에서 봇과 대화를 시작하고 /test 명령어를 입력해보세요")
        
        async def test_polling():
            try:
                # 봇 정보 확인
                bot_info = await bot_handler.application.bot.get_me()
                logger.info(f"✅ 봇 연결 성공: @{bot_info.username} ({bot_info.first_name})")
                
                # 테스트 메시지 전송
                test_message = "🧪 봇 polling 테스트가 시작되었습니다!\n\n/test 명령어를 입력해서 봇이 응답하는지 확인해보세요."
                await bot_handler.application.bot.send_message(
                    chat_id=CHAT_ID,
                    text=test_message
                )
                logger.info("✅ 테스트 메시지 전송 완료")
                
                return True
                
            except Exception as e:
                logger.error(f"❌ 봇 테스트 실패: {e}")
                return False
        
        result = asyncio.run(test_polling())
        
        if result:
            logger.info("🎉 봇 polling 테스트 완료! 이제 텔레그램에서 명령어를 입력해보세요.")
        
        return result
        
    except Exception as e:
        logger.error(f"❌ 봇 polling 테스트 중 오류: {e}")
        return False


if __name__ == "__main__":
    # 테스트 실행
    logger.info("텔레그램 알림 시스템 테스트 시작")
    
    # 1. 연결 테스트
    print("=== 텔레그램 연결 테스트 ===")
    if test_telegram_connection():
        print("✅ 텔레그램 연결 성공!")
    else:
        print("❌ 텔레그램 연결 실패")
        print("\n설정 확인:")
        print(f"- BOT_TOKEN: {'설정됨' if BOT_TOKEN != 'YOUR_BOT_TOKEN_HERE' else '❌ 미설정'}")
        print(f"- CHAT_ID: {'설정됨' if CHAT_ID != 0 else '❌ 미설정'}")
        print("\n환경변수 설정 방법:")
        print("  export TELEGRAM_BOT_TOKEN='여기에_봇_토큰'")
        print("  export TELEGRAM_CHAT_ID='여기에_채팅_ID'")
        exit(1)
    
    # 2. 테스트 알림 전송
    print("\n=== 테스트 알림 전송 ===")
    test_slots = [
        "2025-01-30 18:30:00",
        "2025-01-30 20:00:00", 
        "2025-01-31 14:20:00"
    ]
    
    if send_notification(test_slots):
        print("✅ 테스트 알림 전송 성공!")
    else:
        print("❌ 테스트 알림 전송 실패")
    
    print("\n=== 테스트 완료 ===")


def send_status_notification(status_message: str) -> bool:
    """
    모니터링 상태 메시지를 텔레그램으로 전송
    
    Args:
        status_message: 상태 메시지 텍스트
        
    Returns:
        bool: 전송 성공 여부
    """
    try:
        notifier = TelegramNotifier()
        
        if not notifier.bot:
            logger.error("텔레그램 봇 초기화 실패로 상태 메시지를 보낼 수 없습니다")
            return False
        
        # 비동기 함수를 동기적으로 실행
        result = asyncio.run(notifier._send_status_message_async(status_message))
        
        if result:
            logger.debug("상태 메시지 전송 성공")
            return True
        else:
            logger.warning("상태 메시지 전송 실패")
            return False
            
    except Exception as e:
        logger.error(f"상태 메시지 전송 중 오류: {e}")
        return False 