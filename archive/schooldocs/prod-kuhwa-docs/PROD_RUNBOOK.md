# Kuhwa Docs Prod/Test 운영 런북

이 폴더는 재배포 시 삽질을 줄이기 위한 최소 실행 묶음입니다.

## 포함 파일
- `postdeploy.sh`: 공용 진입 스크립트 (test/prod 선택)
- `prod-postdeploy.sh`: 실제 처리 로직 (시크릿 연결, env 설정, 이미지 배포)
- `PROD_RUNBOOK.md`: 현재 문서

## 사전 조건
- Azure CLI 로그인 완료 (`az login`)
- Docker / buildx 사용 가능
- 대상 인프라가 이미 배포되어 있어야 함 (`infra/deploy-interactive.sh` 완료 상태)

## 재발 방지 핵심 원칙
1. `keyvaultref:`는 `az containerapp secret set`에서만 사용합니다.
2. 런타임 환경변수(`--set-env-vars`)는 반드시 `secretref:<secret-name>` 형식으로 사용합니다.
3. `WEBSITES_INCLUDE_CLOUD_CERTS=true`를 반드시 포함합니다.
4. 이미지 이름은 `records-api`로 통일합니다.

## 가장 많이 쓰는 실행 명령

### 0) 폴더 이동 후 바로 실행 (권장)
```bash
cd prod-kuhwa-docs
ENV_SUFFIX=prod ./postdeploy.sh
```

### 1) Prod 실행
```bash
ENV_SUFFIX=prod ./postdeploy.sh
```

### 2) Test 실행
```bash
ENV_SUFFIX=test ./postdeploy.sh
```

### 3) 확인 프롬프트 없이 실행 (CI/자동화)
```bash
ENV_SUFFIX=prod SKIP_CONFIRM=true ./postdeploy.sh
```

### 4) 태그 지정 배포
```bash
ENV_SUFFIX=prod IMAGE_TAG=1.0.0 ./postdeploy.sh
```

### 4-1) Apple Silicon 권장 빌드 방식
스크립트는 아래 방식으로 배포합니다.
```bash
docker buildx build --platform linux/amd64 -t <ACR>/records-api:<TAG> --push ./apps/records-api
```

### 5) AI 시크릿 동시 반영
```bash
ENV_SUFFIX=prod \
AI_SERVICE_KEY="YOUR_OPENAI_KEY" \
AZURE_OPENAI_ENDPOINT="https://YOUR_RESOURCE.openai.azure.com/" \
./postdeploy.sh
```

### 6) SMS 시크릿 포함
```bash
ENV_SUFFIX=prod \
INCLUDE_SMS_SECRETS=true \
SMS_API_KEY="YOUR_SMS_KEY" \
SMS_API_SECRET="YOUR_SMS_SECRET" \
SMS_SENDER_PHONE="010XXXXXXXX" \
./postdeploy.sh
```

## 기본 동작 요약
`prod-postdeploy.sh`는 아래 순서로 동작합니다.
1. 구독/리소스 대상 검증
2. UAMI 권한 사전 점검 (Key Vault/ACR)
2. Key Vault 필수 시크릿 검사
3. Container App secret 등록 (`keyvaultref`)
4. 런타임 env 주입 (`secretref`)
5. `WEBSITES_INCLUDE_CLOUD_CERTS=true` 적용
6. `records-api` 이미지를 linux/amd64로 빌드/푸시
7. Container App 이미지 업데이트

권한 점검을 건너뛰려면 아래 옵션을 사용합니다.
```bash
SKIP_PERMISSION_CHECK=true ENV_SUFFIX=prod ./postdeploy.sh
```

## 중요 규칙
- env에는 `keyvaultref`를 직접 넣지 않고, 반드시 `secretref`를 사용해야 합니다.
- 관리자 API 테스트 전에는 먼저 로그인 URL로 인증합니다.
  - `https://<FQDN>/.auth/login/aad`

## 관리자 API 테스트 순서
1. 브라우저에서 먼저 로그인 URL 접근
  - `https://<FQDN>/.auth/login/aad`
2. 같은 브라우저 세션에서 관리자 API 호출
  - `https://<FQDN>/api/manage/pending`
3. `Allow unauthenticated access` 설정에서는 자동 로그인 리디렉션이 없으므로 수동 로그인 후 접근해야 합니다.

## 배포 후 빠른 점검
```bash
az containerapp show -n <APP_NAME> -g <RG_NAME> --query "properties.template.containers[0].env" -o table
az containerapp revision list -n <APP_NAME> -g <RG_NAME> --query "[].{name:name,weight:properties.trafficWeight,active:properties.active}" -o table
```

정상 기준:
- 최신 revision weight가 100
- DB/Storage/AI 관련 env가 SecretRef로 표시
- `/api/status`가 JSON 응답

## 배포 후 최종 검증 (5가지)
1. 환경변수 SecretRef 확인
  - `az containerapp show -n $APP -g $RG --query "properties.template.containers[0].env" -o table`
2. 최신 revision 트래픽 weight 100 확인
  - `az containerapp revision list -n $APP -g $RG --query "[].{name:name,weight:properties.trafficWeight,active:properties.active}" -o table`
3. `/api/status` JSON 응답 확인
  - `curl -X POST https://$FQDN/api/status -H "Content-Type: application/json" -d '{"name":"홍길동","birthdate":"1990-01-01"}'`
4. 관리자 API 접근 확인
  - 브라우저에서 `/.auth/login/aad` -> `/api/manage/pending`
5. 시스템 로그 오류 확인
  - `az containerapp logs show -n $APP -g $RG --type system --tail 100 | grep -i error`

## 장애 대응 요약
- `Records storage is unavailable`
  - env가 `secretref:` 형식인지 확인
  - `WEBSITES_INCLUDE_CLOUD_CERTS=true` 확인
  - 시스템 로그에서 Key Vault sync 오류 확인
- `Unauthorized` (관리자 API)
  - `/.auth/login/aad`로 먼저 로그인
  - Cosmos `admins` 컨테이너에 해당 이메일 문서 존재 확인
