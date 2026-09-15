#!/usr/bin/env python3
"""
Papertrail 앱 배포 CLI (Python 진입점)

앱 이미지 빌드 및 컨테이너 앱 업데이트를 수행합니다.
기존 Bash 스크립트(cli/deploy-app.sh)를 호출합니다.
"""

import os
import sys
import subprocess
import argparse
import logging
from pathlib import Path

def find_repo_root() -> Path:
    """프로젝트 루트 디렉토리 반환 (papertrail/의 부모)"""
    script_dir = Path(__file__).resolve().parent
    papertrail_dir = script_dir.parent
    if papertrail_dir.name != 'papertrail':
        raise RuntimeError(f'Expected parent directory name "papertrail", got {papertrail_dir.name}')
    repo_root = papertrail_dir.parent
    return repo_root


def load_config(repo_root: Path) -> None:
    """
    .env 파일에서 환경 변수를 로드합니다.
    core/config.sh와 호환되는 형식을 따릅니다.
    """
    env_file = repo_root / '.env'
    if not env_file.is_file():
        # .env 파일이 없으면 기본값을 사용하며 환경 변수는 이미 설정되어 있을 수 있습니다.
        return

    import re
    with open(env_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            # 키=값 형식 파싱
            match = re.match(r'^\s*([\w\.]+)\s*=\s*(.*?)\s*$', line)
            if match:
                key, value = match.groups()
                # 값에서 후행 주석 제거
                value = value.split('#')[0].strip()
                os.environ[key] = value


def setup_logging() -> None:
    """
    기본 로깅을 구성합니다.
    JSON 형식 로깅을 원한다면 추가 구현이 필요합니다.
    """
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

def run_python_deploy_app(non_interactive: bool = False) -> int:
    """
    Python 모듈을 사용하여 앱 배포 워크플로우를 실행합니다.

    Args:
        non_interactive: 대화형 입력 없이 실행 (필요한 값은 환경 변수로 설정)
    Returns:
        종료 코드
    """
    repo_root = find_repo_root()
    # 구성 및 로깅 초기화
    load_config(repo_root)
    setup_logging()

    # 공통 라이브러리 경로 추가
    common_lib_path = repo_root / 'common-lib'
    if str(common_lib_path) not in sys.path:
        sys.path.insert(0, str(common_lib_path))

    # 모듈 임포트
    try:
        from infrastructure.azure.acr import acr_build_and_push
        from infrastructure.azure.containerapps import update_container_app_image, wait_for_revision_ready, get_container_app_fqdn
        from infrastructure.azure.utils import ensure_azure_login
        from domain.resource_selector import select_resource_group
        from core.naming import generate_names_from_rg
        # 추가 임포트 필요
    except ImportError as e:
        print(f'모듈 임포트 오류: {e}', file=sys.stderr)
        return 1

    # Azure 로그인 확인
    ensure_azure_login()

    # Dockerfile 존재 확인
    app_dir = repo_root / 'apps' / 'records-api'
    dockerfile = app_dir / 'Dockerfile'
    if not dockerfile.is_file():
        print(f'오류: Dockerfile을 찾을 수 없습니다: {dockerfile}', file=sys.stderr)
        return 1

    # 배포 대상 환경 선택
    selected_rg = select_resource_group()
    print(f'선택된 리소스 그룹: {selected_rg}')

    # 리소스 그룹에서 이름 파싱
    # generate_names_from_rg 호출 (임시)
    # TODO: 실제 구현
    acr_name = 'acr' + selected_rg.split('-')[-1]
    app_name = 'app-' + selected_rg.split('-')[-1]

    # 이미지 태그 생성
    from datetime import datetime
    tag = f'manual-{datetime.now().strftime("%Y%m%d%H%M%S")}'
    full_image = f'{acr_name}.azurecr.io/records-api:{tag}'
    print(f'이미지 태그: {tag}')

    # ACR 이미지 빌드
    acr_build_and_push(acr_name, f'records-api:{tag}', str(dockerfile), str(app_dir))

    # 컨테이너 앱 이미지 업데이트
    update_container_app_image(app_name, selected_rg, full_image)

    # 리비전 준비 완료 대기
    wait_for_revision_ready(app_name, selected_rg, 90, 10)

    # 스모크 테스트
    fqdn = get_container_app_fqdn(app_name, selected_rg)
    if fqdn:
        print(f'엔드포인트: https://{fqdn}')
        # smoke_test_container_app(fqdn) # TODO: 구현
    else:
        print('경고: FQDN을 가져올 수 없습니다. 스모크 테스트를 건너뜁니다.')

    print('배포 완료')
    return 0

def main() -> int:
    parser = argparse.ArgumentParser(
        description='SchoolDocs 앱 이미지 빌드 및 컨테이너 앱 업데이트',
        epilog='배포 대상 환경은 내부 Bash 스크립트의 대화형 프롬프트에서 선택할 수 있습니다.'
    )
    parser.add_argument(
        '--non-interactive',
        action='store_true',
        help='대화형 입력 없이 실행 (필요한 값은 환경 변수로 설정)'
    )
    parser.add_argument(
        '--version',
        action='version',
        version='Papertrail 앱 배포 CLI 1.0'
    )

    args = parser.parse_args()
    return run_python_deploy_app(non_interactive=args.non_interactive)

if __name__ == '__main__':
    sys.exit(main())