#!/usr/bin/env python3
"""
Papertrail 전체 배포 CLI (Python 진입점)

참조 문서에 따라 CLI 진입점을 Python으로 통일합니다.
common-lib의 모듈을 사용하여 Azure 구독 수준 배포를 실행합니다.
"""

import os
import sys
import json
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
    return papertrail_dir.parent


def find_common_lib() -> Path:
    """common-lib 디렉토리 경로 반환"""
    repo_root = find_repo_root()
    common_lib = repo_root / 'common-lib'
    if not common_lib.is_dir():
        raise RuntimeError(f'common-lib 디렉토리를 찾을 수 없습니다: {common_lib}')
    return common_lib


def load_config(repo_root: Path) -> None:
    """.env 파일에서 환경 변수를 로드합니다."""
    env_file = repo_root / '.env'
    if not env_file.is_file():
        return

    import re
    with open(env_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            match = re.match(r'^\s*([\w\.]+)\s*=\s*(.*?)\s*$', line)
            if match:
                key, value = match.groups()
                value = value.split('#')[0].strip()
                os.environ[key] = value


def setup_logging() -> None:
    """기본 로깅을 구성합니다."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def select_env() -> str:
    """배포 환경을 선택합니다."""
    print()
    print("환경 선택")
    print("1. 테스트")
    print("2. 운영")
    print("-----")
    while True:
        try:
            choice = input("번호 입력 (1-2): ").strip()
        except EOFError:
            print("\n입력이 취소되었습니다.", file=sys.stderr)
            sys.exit(1)
        if choice == '1':
            return 't'
        elif choice == '2':
            return 'p'
        else:
            print("[WARN] 1 또는 2를 입력하세요.", file=sys.stderr)


def run_python_deploy(what_if: bool = False, non_interactive: bool = False) -> int:
    """common-lib 모듈을 사용하여 배포 워크플로우를 실행합니다."""
    repo_root = find_repo_root()
    common_lib = find_common_lib()

    # .env 로드
    load_config(repo_root)

    # 로깅 설정
    setup_logging()
    logger = logging.getLogger(__name__)

    # common-lib을 sys.path에 추가
    common_lib_str = str(common_lib)
    if common_lib_str not in sys.path:
        sys.path.insert(0, common_lib_str)

    # 모듈 임포트
    try:
        from infrastructure.azure.deploy import run_deployment, run_whatif
        from infrastructure.azure.utils import ensure_azure_login
        from infrastructure.azure.shared_infra import ensure_shared_infrastructure, get_subscription_id
        from core.naming import generate_resource_names, generate_shared_names
        from core.config import LOCATION, REGION_CODE, TEMPLATE_FILE
        from domain.school import input_school_info, save_school_info, load_school_info, school_info_file
        from domain.interactive import select_school_level
        from domain.deploy_selector import resolve_deploy_num
    except ImportError as e:
        logger.error('모듈 임포트 오류: %s', e)
        return 1

    # Azure 로그인 확인
    ensure_azure_login()

    # 환경 선택
    if non_interactive:
        env_short = os.environ.get('ENV_SHORT', 't')
    else:
        env_short = select_env()

    # 학교 정보 입력
    if non_interactive:
        school_name_token = os.environ.get('SCHOOL_NAME_TOKEN', 'test')
        nice_code = os.environ.get('NICE_CODE', 'sen')
        school_level = os.environ.get('SCHOOL_LEVEL', 'hs')
        school_info = {
            'school_name_token': school_name_token,
            'nice_code': nice_code,
            'school_level': school_level,
        }
    else:
        # 기존 학교 정보 파일 검색 (papertrail/schools/)
        schools_dir = repo_root / 'schools'
        school_files = sorted(schools_dir.glob('*.json')) if schools_dir.is_dir() else []

        if school_files:
            print()
            print("저장된 학교 정보를 불러옵니다:")
            for i, f in enumerate(school_files, 1):
                data = load_school_info(str(f))
                if data:
                    name = data.get('school_korean_name', '?')
                    token = data.get('school_name_token', '?')
                    level = data.get('school_level', '?')
                    nice = data.get('nice_code', '?')
                    print(f"{i}. {name} ({token}, {nice}, {level})")
            print(f"{len(school_files)+1}. 새로 입력")
            print("-----")
            while True:
                try:
                    choice = input(f"번호 입력 (1-{len(school_files)+1}): ").strip()
                except EOFError:
                    print("\n입력이 취소되었습니다.", file=sys.stderr)
                    sys.exit(1)
                if choice.isdigit():
                    idx = int(choice)
                    if 1 <= idx <= len(school_files):
                        school_info = load_school_info(str(school_files[idx-1]))
                        if school_info:
                            break
                    elif idx == len(school_files) + 1:
                        school_info = input_school_info()
                        break
                print(f"[WARN] 1~{len(school_files)+1} 중에서 선택하세요.", file=sys.stderr)
        else:
            print()
            print("저장된 학교 정보가 없습니다. 학교 정보를 입력해주세요.")
            school_info = input_school_info()

        school_name_token = school_info.get('school_name_token', 'test')
        nice_code = school_info.get('nice_code', 'sen')
        school_level = school_info.get('school_level', 'hs')

    # 배포 번호 결정
    env_suffix = 'test' if env_short == 't' else 'prod'
    prefix = f'rg-{school_name_token}-{nice_code}-{school_level}-{REGION_CODE}'
    if non_interactive:
        deploy_num = os.environ.get('DEPLOY_NUM', '01')
    else:
        deploy_num = resolve_deploy_num(prefix, LOCATION)

    # 리소스명 생성
    names = generate_resource_names(school_name_token, nice_code, school_level, env_short, deploy_num)
    logger.info('리소스 그룹: %s', names.get('RESOURCE_GROUP', 'N/A'))

    # Azure 리소스명을 학교 정보에 추가하여 저장
    if not non_interactive:
        school_info['deploy_num'] = deploy_num
        school_info['env_suffix'] = env_suffix
        school_info['region_code'] = REGION_CODE
        school_info['location'] = LOCATION
        school_info.update(names)
        out_file = str(schools_dir / f'{school_name_token}{nice_code}{school_level}{env_short}.json')
        save_school_info(school_info, out_file)
        print(f"[INFO] 학교 정보 저장 완료: {out_file}")

    # === 공유 인프라 (share-infra) ===
    # Cosmos DB (free tier, 구독당 1개)와 Container App Environment (리전당 1개)는
    # 공유 리소스 그룹에 생성하고 모든 학교 배포가 참조함
    shared_names = generate_shared_names(school_name_token, nice_code, school_level, REGION_CODE)
    shared_rg = shared_names['SHARED_RG']
    shared_cosmos = shared_names['SHARED_COSMOS']
    shared_env = shared_names['SHARED_ENV']

    print()
    print(f"[INFO] 공유 인프라 확인: RG={shared_rg}, Cosmos={shared_cosmos}, CAE={shared_env}")

    # 공유 인프라가 없으면 생성
    ensure_shared_infrastructure(LOCATION, shared_rg, shared_cosmos, shared_env)

    # 공유 Cosmos DB에 대한 Identity 권한 부여 확인
    identity_name = names.get('IDENTITY', f'id-{school_name_token}{nice_code}{school_level}{env_short}{deploy_num}')
    identity_rg = names.get('RESOURCE_GROUP', f'rg-{school_name_token}{nice_code}{school_level}{REGION_CODE}{deploy_num}')

    def grant_cosmos_role(principal_id: str) -> None:
        """공유 Cosmos DB에 Identity에게 Cosmos DB Built-in Data Contributor 역할을 부여합니다.
        
        Cosmos DB 데이터 플레인 RBAC는 `az cosmosdb sql role assignment` 명령어를 사용합니다.
        """
        role_def_id = '00000000-0000-0000-0000-000000000002'  # Cosmos DB Built-in Data Contributor
        try:
            # 기존 할당 확인
            role_check = subprocess.run(
                ['az', 'cosmosdb', 'sql', 'role', 'assignment', 'list',
                 '--account-name', shared_cosmos, '--resource-group', shared_rg,
                 '--query', f'[?principalId==`{principal_id}`]', '-o', 'json'],
                capture_output=True, text=True
            )
            if role_check.returncode == 0:
                existing = json.loads(role_check.stdout) if role_check.stdout.strip() else []
                if existing:
                    print(f"[INFO] 공유 Cosmos DB 권한 이미 부여됨")
                    return
            print(f"[INFO] 공유 Cosmos DB({shared_cosmos})에 Identity 권한 부여 중...")
            subprocess.run(
                ['az', 'cosmosdb', 'sql', 'role', 'assignment', 'create',
                 '--account-name', shared_cosmos, '--resource-group', shared_rg,
                 '--role-definition-id', role_def_id,
                 '--principal-id', principal_id,
                 '--scope', '/', '--output', 'none'],
                check=True, capture_output=True, text=True
            )
            print(f"[INFO] 권한 부여 완료")
        except subprocess.CalledProcessError as e:
            print(f"[WARN] 권한 부여 실패: {e.stderr.strip() if e.stderr else e}", file=sys.stderr)

    identity_pending = False
    try:
        identity_result = subprocess.run(
            ['az', 'identity', 'show', '--name', identity_name, '--resource-group', identity_rg,
             '--query', 'principalId', '-o', 'tsv'],
            capture_output=True, text=True
        )
        if identity_result.returncode == 0 and identity_result.stdout.strip():
            grant_cosmos_role(identity_result.stdout.strip())
        else:
            identity_pending = True
    except FileNotFoundError:
        pass

    if identity_pending:
        print(f"[INFO] Identity({identity_name})가 아직 없습니다. 배포 후 권한 부여가 필요합니다.")

    # 공유 Cosmos DB와 CAE 정보를 파라미터로 설정
    existing_cosmos_name = shared_cosmos
    existing_cosmos_rg = shared_rg

    # CAE 확인: shared_infra에서 설정한 환경 변수 우선 사용
    existing_env_name = os.environ.get('SHARED_ENV_NAME', shared_env)
    existing_env_rg = os.environ.get('SHARED_ENV_RG', shared_rg)
    if not os.environ.get('SHARED_ENV_ID'):
        # 환경 변수에 없으면 직접 확인
        try:
            env_check = subprocess.run(
                ['az', 'containerapp', 'env', 'show', '--name', shared_env, '--resource-group', shared_rg,
                 '--query', '{name:name, rg:resourceGroup}', '-o', 'json'],
                capture_output=True, text=True
            )
            if env_check.returncode == 0 and env_check.stdout.strip():
                env_data = json.loads(env_check.stdout)
                existing_env_name = env_data['name']
                existing_env_rg = env_data.get('rg', shared_rg)
            else:
                # 지정된 CAE가 없으면 같은 리전의 기존 CAE 검색
                env_list = subprocess.run(
                    ['az', 'containerapp', 'env', 'list', '--query', '[].{name:name, rg:resourceGroup, location:location}', '-o', 'json'],
                    capture_output=True, text=True
                )
                if env_list.returncode == 0 and env_list.stdout.strip():
                    envs = json.loads(env_list.stdout)
                    # 같은 리전의 CAE 우선 선택
                    same_region = [e for e in envs if e.get('location', '').replace(' ', '').lower() == LOCATION.replace(' ', '').lower()]
                    if same_region:
                        env = same_region[0]
                    elif envs:
                        env = envs[0]
                    else:
                        env = None
                    if env:
                        existing_env_name = env['name']
                        existing_env_rg = env['rg']
                        print(f"[INFO] 기존 Container Apps Environment 사용: {existing_env_name} (리소스 그룹: {existing_env_rg})")
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    # 템플릿 파일 경로 (common-lib 기준 상대 경로)
    template_rel = os.environ.get('TEMPLATE_FILE', 'deploy/infra/main.subscription.bicep')
    template_path = str(common_lib / template_rel)
    logger.info('템플릿 파일: %s', template_path)

    # 배포 파라미터 준비
    params = [
        f'location={LOCATION}',
        f'schoolNameToken={school_name_token}',
        f'schoolLevel={school_level}',
        f'envSuffix={env_suffix}',
        f'deployNum={deploy_num}',
        f'regionCode={REGION_CODE}',
        'enableCosmosFreeTier=false',
        'configureRuntimeSecrets=false',
        'containerPort=80',
        'probePath=/',
        'minReplicas=0',
        'maxReplicas=2',
        'enableIpRestriction=false',
        'allowedCidrs=[]',
        'corsAllowedOrigins=[]',
    ]
    if existing_env_name:
        params.append(f'existingContainerAppEnvName={existing_env_name}')
        if existing_env_rg:
            params.append(f'existingContainerAppEnvResourceGroup={existing_env_rg}')
    if existing_cosmos_name:
        params.append(f'existingCosmosDbName={existing_cosmos_name}')
        if existing_cosmos_rg:
            params.append(f'existingCosmosDbResourceGroup={existing_cosmos_rg}')

    deployment_name = f'deploy-{school_name_token}-{deploy_num}'

    # what-if (선택)
    if what_if:
        run_whatif(deployment_name, template_path, params)
        if not non_interactive:
            from domain.interactive import confirm_yn
            if not confirm_yn('계속 배포할까요? (y/N): '):
                return 0

    # 배포 실행
    success = run_deployment(deployment_name, template_path, params)

    if success and existing_cosmos_name:
        # 공유 Cosmos DB를 사용하는 경우, 연결 문자열을 Key Vault에 설정
        # (Bicep에서 cosmosConnectionSecret이 생성되지 않으므로 별도 처리)
        kv_name = names.get('KEY_VAULT', f'kv-{school_name_token}-{school_level}-{env_suffix}-{REGION_CODE}{deploy_num}')
        try:
            print(f"[INFO] 공유 Cosmos DB 연결 문자열을 Key Vault({kv_name})에 설정 중...")
            cosmos_keys = subprocess.run(
                ['az', 'cosmosdb', 'keys', 'list', '--name', existing_cosmos_name,
                 '--resource-group', existing_cosmos_rg, '--query', 'primaryMasterKey', '-o', 'tsv'],
                capture_output=True, text=True
            )
            if cosmos_keys.returncode == 0 and cosmos_keys.stdout.strip():
                conn_str = f'AccountEndpoint=https://{existing_cosmos_name}.documents.azure.com:443/;AccountKey={cosmos_keys.stdout.strip()};'
                subprocess.run(
                    ['az', 'keyvault', 'secret', 'set', '--vault-name', kv_name,
                     '--name', 'connection-string-database', '--value', conn_str,
                     '--output', 'none'],
                    check=True, capture_output=True, text=True
                )
                print(f"[INFO] 공유 Cosmos DB 연결 문자열 설정 완료")
        except subprocess.CalledProcessError as e:
            print(f"[WARN] 공유 Cosmos DB 연결 문자열 설정 실패: {e.stderr.strip() if e.stderr else e}", file=sys.stderr)
        except FileNotFoundError:
            pass

        # 배포 전 Identity가 없어서 권한 부여를 못한 경우, 배포 후 재시도
        if identity_pending:
            print(f"[INFO] 배포 완료. Identity({identity_name}) 권한 부여 재시도...")
            try:
                identity_result = subprocess.run(
                    ['az', 'identity', 'show', '--name', identity_name, '--resource-group', identity_rg,
                     '--query', 'principalId', '-o', 'tsv'],
                    capture_output=True, text=True
                )
                if identity_result.returncode == 0 and identity_result.stdout.strip():
                    grant_cosmos_role(identity_result.stdout.strip())
                else:
                    print(f"[WARN] Identity({identity_name})를 찾을 수 없습니다. 수동으로 권한 부여가 필요합니다.", file=sys.stderr)
            except FileNotFoundError:
                pass

    return 0 if success else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description='SchoolDocs Azure 인프라 배포',
        epilog='추가 옵션은 내부 Bash 스크립트의 대화형 프롬프트에서 설정할 수 있습니다.'
    )
    parser.add_argument(
        '--what-if',
        action='store_true',
        help='배포 전 what-if 시뮬레이션 실행'
    )
    parser.add_argument(
        '--non-interactive',
        action='store_true',
        help='대화형 입력 없이 실행 (필요한 값은 환경 변수로 설정)'
    )
    parser.add_argument(
        '--version',
        action='version',
        version='Papertrail 배포 CLI 1.0'
    )

    args = parser.parse_args()
    return run_python_deploy(what_if=args.what_if, non_interactive=args.non_interactive)


if __name__ == '__main__':
    sys.exit(main())
