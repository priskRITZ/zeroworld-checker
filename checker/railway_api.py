# -*- coding: utf-8 -*-
"""
Railway API 클라이언트 모듈

Railway GraphQL API를 사용해서 서비스 설정을 변경하는 기능 제공
"""

import os
import aiohttp
import asyncio
from typing import Optional, Dict, Any
from loguru import logger

from .config import BRANCH_THEME_MAPPING


class RailwayAPI:
    """Railway GraphQL API 클라이언트"""
    
    def __init__(self, api_token: Optional[str] = None):
        self.api_token = api_token or os.getenv("RAILWAY_API_TOKEN")
        self.graphql_url = "https://backboard.railway.com/graphql/v2"
        
        if not self.api_token:
            logger.warning("Railway API 토큰이 설정되지 않았습니다. 환경변수 RAILWAY_API_TOKEN을 설정하세요.")
    
    async def _execute_query(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """GraphQL 쿼리 실행"""
        if not self.api_token:
            raise ValueError("Railway API 토큰이 설정되지 않았습니다")
        
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }
        
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.graphql_url,
                json=payload,
                headers=headers
            ) as response:
                result = await response.json()
                
                if response.status != 200:
                    logger.error(f"Railway API 요청 실패: {response.status} - {result}")
                    raise Exception(f"Railway API 오류: {result}")
                
                if "errors" in result:
                    logger.error(f"GraphQL 오류: {result['errors']}")
                    raise Exception(f"GraphQL 오류: {result['errors']}")
                
                return result
    
    async def get_project_services(self, project_id: str) -> Dict[str, Any]:
        """프로젝트의 서비스 목록 조회"""
        query = """
        query getProject($projectId: String!) {
            project(id: $projectId) {
                id
                name
                services {
                    edges {
                        node {
                            id
                            name
                            source {
                                repo
                                branch
                            }
                        }
                    }
                }
            }
        }
        """
        
        variables = {"projectId": project_id}
        return await self._execute_query(query, variables)
    
    async def get_service_info(self, service_id: str) -> Dict[str, Any]:
        """서비스 정보 조회 (service(id: ...) 직접 조회)"""
        query = """
        query getService($id: String!) {
            service(id: $id) {
                id
                name
                source {
                    repo
                    branch
                }
            }
        }
        """

        variables = {"id": service_id}
        logger.info(f"서비스 {service_id} 정보 조회 중 (service 쿼리)...")
        result = await self._execute_query(query, variables)
        logger.info(f"서비스 응답: {result}")
        return result

    async def update_service_branch(self, service_id: str, branch: str) -> Dict[str, Any]:
        """서비스의 소스 브랜치 변경"""
        query = """
        mutation serviceUpdate($serviceId: String!, $branch: String!) {
          serviceUpdate(
            id: $serviceId
            input: {
              source: {
                branch: $branch
              }
            }
          ) {
            id
          }
        }
        """
        variables = {"serviceId": service_id, "branch": branch}
        return await self._execute_query(query, variables)

    async def trigger_deployment(self, service_id: str) -> Dict[str, Any]:
        """서비스 재배포 트리거"""
        query = """
        mutation deploymentTrigger($serviceId: String!) {
          deploymentTrigger(
            serviceId: $serviceId
          ) {
            id
            status
          }
        }
        """
        variables = {"serviceId": service_id}
        return await self._execute_query(query, variables)



async def switch_to_branch_cli(branch_name: str) -> bool:
    """
    Railway CLI를 사용한 브랜치 전환 (대안 방법)
    """
    try:
        import subprocess
        import os
        
        logger.info(f"🚂 Railway CLI로 브랜치 '{branch_name}' 전환 시도...")
        
        # Railway CLI 명령어 실행
        result = subprocess.run([
            "railway", "service", "update", 
            "--source-branch", branch_name
        ], capture_output=True, text=True, cwd="/app" if os.path.exists("/app") else ".")
        
        if result.returncode == 0:
            logger.info(f"✅ Railway CLI로 브랜치 '{branch_name}' 전환 성공")
            return True
        else:
            logger.error(f"❌ Railway CLI 실패: {result.stderr}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Railway CLI 브랜치 전환 실패: {e}")
        return False

async def switch_to_branch(branch_name: str) -> bool:
    """
    지정된 브랜치로 전환하고 재배포 (CLI 사용)
    
    Args:
        branch_name: 전환할 브랜치 이름 ("main", "test" 등)
    
    Returns:
        bool: 성공 여부
    """
    try:
        logger.info(f"🔧 브랜치 '{branch_name}' 전환 시도 (CLI 방식)...")
        
        if branch_name not in BRANCH_THEME_MAPPING:
            logger.error(f"❌ 지원하지 않는 브랜치: {branch_name}")
            logger.error(f"   지원하는 브랜치: {list(BRANCH_THEME_MAPPING.keys())}")
            return False
            
        # Railway CLI를 사용하여 브랜치 전환
        success = await switch_to_branch_cli(branch_name)
        
        if success:
            logger.info(f"✅ {branch_name} 브랜치로 성공적으로 전환되었습니다.")
        else:
            logger.error(f"❌ {branch_name} 브랜치로 전환하는 중 오류가 발생했습니다.")
            
        return success

    except Exception as e:
        logger.error(f"❌ 브랜치 전환 실패: {type(e).__name__}: {str(e)}")
        return False


def test_railway_settings() -> bool:
    """
    Railway API 설정 상태 확인
    
    Returns:
        bool: 모든 필수 설정이 완료되었는지 여부
    """
    try:
        import os
        
        # 환경변수 확인
        api_token = os.getenv("RAILWAY_API_TOKEN")
        project_id = os.getenv("RAILWAY_PROJECT_ID") 
        service_id = os.getenv("RAILWAY_SERVICE_ID")
        
        logger.info("🔧 Railway API 설정 상태:")
        logger.info(f"  - RAILWAY_API_TOKEN: {'✅ 설정됨' if api_token else '❌ 미설정'}")
        logger.info(f"  - RAILWAY_PROJECT_ID: {'✅ 설정됨' if project_id else '❌ 미설정'}")
        logger.info(f"  - RAILWAY_SERVICE_ID: {'✅ 설정됨' if service_id else '❌ 미설정'}")
        
        missing_vars = []
        if not api_token:
            missing_vars.append("RAILWAY_API_TOKEN")
        if not service_id:
            missing_vars.append("RAILWAY_SERVICE_ID")
            
        if missing_vars:
            logger.error(f"\n❌ 누락된 환경변수: {', '.join(missing_vars)}")
            logger.error("\n📖 설정 방법:")
            logger.error("1. Railway 대시보드 (railway.app) 접속")
            logger.error("2. 프로젝트 선택 → Settings → Tokens")
            logger.error("3. 새 토큰 생성 후 RAILWAY_API_TOKEN에 설정")
            logger.error("4. 서비스 페이지에서 Service ID 복사 후 RAILWAY_SERVICE_ID에 설정")
            logger.error("\n🔧 Railway 환경변수 설정:")
            logger.error("   Variables 탭에서 위 환경변수들 추가")
            return False
        
        logger.info("\n✅ 모든 필수 환경변수가 설정되었습니다!")
        logger.info("💡 이제 /branch main 또는 /branch test 명령어를 사용할 수 있습니다.")
        return True
        
    except Exception as e:
        logger.error(f"❌ Railway 설정 확인 중 오류: {e}")
        return False


def update_local_theme_config(theme_name: str):
    """
    로컬 config.py 파일의 테마 이름 업데이트
    """
    try:
        config_path = "checker/config.py"
        
        # config.py 파일 읽기
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # THEME_NAME 라인 찾아서 교체
        import re
        pattern = r'THEME_NAME = ".*?"'
        replacement = f'THEME_NAME = "{theme_name}"'
        
        updated_content = re.sub(pattern, replacement, content)
        
        # 파일에 다시 쓰기
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write(updated_content)
        
        logger.info(f"로컬 config 업데이트: THEME_NAME = '{theme_name}'")
        
    except Exception as e:
        logger.error(f"로컬 config 업데이트 실패: {e}")
