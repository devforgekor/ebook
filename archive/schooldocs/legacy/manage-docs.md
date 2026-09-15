다음은 **부관리자 권한 세분화** 및 **인증서 종류별 업로드 경로 분리** 요구사항을 반영한 **최종 기술 설계서(버전 7.3-final)** 전문입니다.

---

# 최종 기술 설계서: 인증서 관리 시스템 (ACA 기반)

**버전 7.3-final | 2026-04-11 | 부관리자 권한 세분화 및 인증서별 업로드 경로 분리 반영**

---

## 목차

1. 시스템 개요
2. 인프라 구성
3. Container Apps 상세 설정
4. Cosmos DB 설계 (단일 컨테이너)
5. Express API 구현 명세 (Easy Auth 적용)
6. PDF 검증 로직 (스트림 기반)
7. PDF 인증서 파싱 및 Unknown 처리
8. AI 보조 인식 파이프라인 (GPT-4o mini Vision)
9. PDF → WebP 변환 파이프라인
10. Dockerfile 및 빌드/배포
11. 모니터링 및 로깅 (다원화 전략)
12. 비용 분석
13. 테스트 시나리오
14. 문제 해결 가이드
15. 유지보수 정책
16. 부록

---

## 1. 시스템 개요

### 1.1 목적 및 배경

- 보안·안전·필수교육 인증서를 3년 단위 기수제로 관리한다.
- 기수당 1회 제출 원칙, 중복 제출 시 파일 해시 비교 → 최초 제출 연도 보존.
- 누적 이수자 보고 (제출 연도 기준)가 가능해야 한다.
- 관리자는 **전체관리자(Super)** 와 **부관리자(Sub)** 로 구분하며, 부관리자는 담당 인증서 종류에만 접근할 수 있다.

### 1.2 핵심 비기능 요구사항

| 요구사항 | 설명 |
|----------|------|
| 비용 | 월 $0 (Azure 무료 할당량 내) |
| 성능 | 평일 08:30~17:30 콜드 스타트 없음 (주말·공휴일 0 replica). HTTPS 무료 제공. |
| 보안 | 개인정보 AES-256 암호화, HMAC 해시, Key Vault로 키 관리. 관리자 인증은 M365 Easy Auth. 모든 비밀 정보 Key Vault + Managed Identity. |
| 유지보수 | 인프라 설정 후 거의 손댈 일 없음 (KEDA Cron 자동화). |

### 1.3 기술 스택

| 계층 | 기술 | 비고 |
|------|------|------|
| 호스팅 | Azure Container Apps (Consumption Plan) | HTTPS 기본 제공, KEDA 스케일링, 무료 할당량 |
| 실행 환경 | Node.js 20 + Express | 표준 Node.js 서버 (커스텀 컨테이너) |
| 데이터베이스 | Azure Cosmos DB (NoSQL) | 단일 컨테이너 main + admins + ai_limits, 무료 티어 1000 RU/s |
| 스토리지 | Azure Storage Account (Cool Tier) | WebP 이미지 저장, Lifecycle 5년 |
| 키 관리 | Azure Key Vault (Standard) | AES-256 키, HMAC 키 |
| 컨테이너 레지스트리 | Azure Container Registry (ACR) | 이미지 저장 (ACR 전용) |
| 모니터링 | Console 로그 (기본), Log Analytics (Audit), App Insights (Error/Metrics) | 목적별 분리, 비용 통제 |
| 인증 | Microsoft Entra ID (Easy Auth) | 관리자 로그인 전용, 사용자 API 무인증 |
| PDF 파싱 | pdf-parse | 경량 텍스트 추출, 헤더 검증 추가 |
| AI 보조 인식 | Azure OpenAI GPT-4o mini (Vision) | 규칙 파싱 실패 시에만 호출, 저비용, 호출 상한 적용 |
| 운영 자동화 | KEDA Cron (ACA 내장) | 평일 08:30~17:30 minReplicas=1 |

---

## 2. 인프라 구성

### 2.1 리소스 그룹 및 이름

- 리소스 그룹: `rg-<school>-<level>-<env>-krc01` (예: `rg-seoul-hs-prod-krc01`)
- Cosmos DB: `cosmos-<school>-<level>-<env>-krc01`
  - Database: `CertificateSystem`
  - Containers: `records`, `admins`, `registry`, `ai_limits`
- Storage Account: `st<school><level><env>krc01`
  - Containers: `record-files`, `webps`
- Key Vault: `kv-<school>-<level>-<env>-krc01`
  - Secrets: `connection-string-storage`, `connection-string-database`, `encryption-key-aes`, `encryption-key-hmac`, `api-key-ai` 등
- Container Registry: `acr<school><level><env>krc01`
- Container Apps Environment: `env-<school>-<level>-<env>-krc01`
- Container App: `app-<school>-<level>-<env>-krc01`
- Log Analytics Workspace: `law-<school>-<level>-<env>-krc01`

### 2.2 네트워킹

- Container Apps는 공용 HTTPS 엔드포인트를 기본 제공한다.
- 학교 내부망만 허용하려면 IP 제한(화이트리스트)을 Ingress 설정으로 추가 가능 (선택 사항).

---

## 3. Container Apps 상세 설정

### 3.1 기본 설정

| 항목 | 값 |
|------|-----|
| Plan | Consumption |
| Region | Korea Central |
| minReplicas | 0 |
| maxReplicas | 2 |
| Ingress | Enabled, port 80 (HTTPS 자동 적용) |
| Authentication | Allow unauthenticated access (익명 API 허용) |
| Managed Identity | 시스템 할당 사용 (Key Vault, ACR 접근) |

### 3.2 스케일링 규칙 (KEDA Cron + HTTP)

```json
"scale": {
  "minReplicas": 0,
  "maxReplicas": 2,
  "rules": [
    {
      "name": "http-rule",
      "http": {
        "metadata": {
          "concurrentRequests": "50"
        }
      }
    },
    {
      "name": "weekday-scale-up",
      "custom": {
        "type": "cron",
        "metadata": {
          "schedule": "30 8 * * 1-5",
          "timezone": "Asia/Seoul",
          "desiredReplicas": "1"
        }
      }
    },
    {
      "name": "weekday-scale-down",
      "custom": {
        "type": "cron",
        "metadata": {
          "schedule": "30 17 * * 1-5",
          "timezone": "Asia/Seoul",
          "desiredReplicas": "0"
        }
      }
    }
  ]
}
```

공휴일 처리: 공휴일에는 별도의 애플리케이션 레벨 처리를 하지 않는다. ACA는 minReplicas=0 상태에서 요청이 들어오면 자동으로 인스턴스를 생성하여 응답한다(콜드 스타트 발생). 따라서 공휴일에도 접속은 가능하며, 서비스 중단 없이 정상 동작한다.

### 3.3 Managed Identity 및 권한

Container App에 User Assigned Managed Identity를 연결하고 다음 역할을 부여한다.

| 리소스 | 역할 | 목적 |
|--------|------|------|
| Container Registry (`acr<school><level><env>krc01`) | AcrPull | 이미지 Pull |
| Key Vault (`kv-<school>-<level>-<env>-krc01`) | Key Vault Secrets User | 시크릿 읽기 |
| Storage Account (`st<school><level><env>krc01`) | Storage Blob Data Contributor | Blob 업로드/다운로드 |

역할 할당 명령어:

```bash
az role assignment create --assignee <principal-id> --role "AcrPull" --scope /subscriptions/.../resourceGroups/<rgName>/providers/Microsoft.ContainerRegistry/registries/<acrName>
az role assignment create --assignee <principal-id> --role "Key Vault Secrets User" --scope /subscriptions/.../resourceGroups/<rgName>/providers/Microsoft.KeyVault/vaults/<keyVaultName>
az role assignment create --assignee <principal-id> --role "Storage Blob Data Contributor" --scope /subscriptions/.../resourceGroups/<rgName>/providers/Microsoft.Storage/storageAccounts/<storageAccountName>
```

### 3.4 Key Vault 시크릿 연결 (secretRef 방식)

1. Container Apps → Secrets → Add
  - `connection-string-database`, `connection-string-storage`, `encryption-key-aes`, `encryption-key-hmac`, `api-key-ai`, `azure-openai-endpoint` 등록
2. Container Apps → Environment variables → Add
  - `DATABASE_CONNECTION_STRING` → Source: Secret, Secret: `connection-string-database`
  - `STORAGE_CONNECTION_STRING` → Source: Secret, Secret: `connection-string-storage`
  - `ENCRYPTION_KEY_AES` → Source: Secret, Secret: `encryption-key-aes`
  - `ENCRYPTION_KEY_HMAC` → Source: Secret, Secret: `encryption-key-hmac`
  - `AI_SERVICE_KEY` → Source: Secret, Secret: `api-key-ai`
  - `AZURE_OPENAI_ENDPOINT` → Source: Secret, Secret: `azure-openai-endpoint`
  - `COSMOS_DATABASE` → 일반 문자열 (`CertificateSystem`)
  - `COSMOS_CONTAINER` / `COSMOS_ADMINS_CONTAINER` / `COSMOS_REGISTRY_CONTAINER` → 일반 문자열
  - `WEBSITES_INCLUDE_CLOUD_CERTS` → 일반 문자열 (`true`)

### 3.5 환경 변수 전체 목록

| 이름 | 값 출처 | 비고 |
|------|---------|------|
| `DATABASE_CONNECTION_STRING` | Secret 참조 | |
| `STORAGE_CONNECTION_STRING` | Secret 참조 | |
| `ENCRYPTION_KEY_HMAC` | Secret 참조 | Key Vault |
| `ENCRYPTION_KEY_AES` | Secret 참조 | Key Vault |
| `AI_SERVICE_KEY` | Secret 참조 | |
| `AZURE_OPENAI_ENDPOINT` | Secret 참조 | |
| `COSMOS_DATABASE` | 일반 문자열 | `CertificateSystem` |
| `COSMOS_CONTAINER` | 일반 문자열 | `records` |
| `COSMOS_ADMINS_CONTAINER` | 일반 문자열 | `admins` |
| `COSMOS_REGISTRY_CONTAINER` | 일반 문자열 | `registry` |
| `STORAGE_CONTAINER` | 일반 문자열 | `record-files` |
| `WEBSITES_INCLUDE_CLOUD_CERTS` | 일반 문자열 | `true` |

### 3.6 Easy Auth (Microsoft Entra ID)

- Authentication → Add identity provider → Microsoft
- Restrict access: Allow unauthenticated access (익명 API 허용)
- 관리자 API는 코드 내에서 `req.headers['x-ms-client-principal-name']`(email)으로 Cosmos DB `admins` 컨테이너 조회 후 권한 확인

⚠️ 주의사항:

- Easy Auth는 전체 앱 단위로 적용된다. 경로별 제어는 코드 내부에서 수행해야 하며, 관리자 API는 반드시 Easy Auth 보호를 받는 상태에서만 호출되어야 한다.
- 익명 API에서는 `x-ms-client-principal-*` 헤더를 신뢰하지 않는다.
- 로컬 개발 환경 테스트: 로컬에서 `x-ms-client-principal-name` 헤더를 수동으로 설정할 수 있으나, 프로덕션 환경에서는 Azure Easy Auth가 이 헤더를 안전하게 주입하므로 외부에서 위조할 수 없다. 내부망 전용 IP 화이트리스트와 함께 사용하면 더욱 안전하다.

---

## 4. Cosmos DB 설계 (단일 컨테이너)

### 4.1 컨테이너 구조

- `main`: 모든 비관리자 데이터 저장 (`cohort`, `member`, `submission`)
- `admins`: 관리자 계정 정보 저장 (`email`, `type`, `name`, `allowedCertificateTypes`)
- `ai_limits`: AI 호출 상한 관리를 위한 TTL 컨테이너

### 4.2 파티션 키

| 컨테이너 | 파티션 키 | 설명 |
|----------|-----------|------|
| `main` | `/cohortId` | cohort 문서는 자신의 id를 cohortId로 사용 |
| `admins` | `/email` | 관리자 이메일 |
| `ai_limits` | `/partitionKey` | `_system` 사용 (고정) |

### 4.3 personId 생성 규칙 (필수)

1. name 정규화: trim() 후 연속 공백을 하나로 축약, 유니코드 NFC 정규화. 대소문자 변환 없음.
2. birthdate 정규화: YYYY-MM-DD 형식만 허용.
3. 결합 문자열: `"personId|" + normalizedName + "|" + birthdateYYYYMMDD`
4. HMAC-SHA256 (Key Vault의 hmac-key 사용)
5. 출력 인코딩: hex (64 characters)

### 4.4 문서 타입 및 예시 (main 컨테이너)

**기수 (type: cohort)**

```json
{
  "id": "cohort_safety_2024_2026",
  "cohortId": "safety_2024-2026",
  "type": "cohort",
  "name": "2024-2026 안전교육",
  "startYear": 2024,
  "endYear": 2026,
  "deadline": "2026-12-31T23:59:59Z",
  "active": true
}
```

> **참고:** `cohortId`의 접두사(`safety`, `health`, `harassment` 등)는 인증서 종류를 식별하며, Blob Storage 업로드 경로 및 부관리자 권한 제어에 사용된다.

**명단 (type: member)**

```json
{
  "id": "member_personId_cohortId",
  "cohortId": "safety_2024-2026",
  "type": "member",
  "personId": "hex",
  "year": 2024,
  "active": true,
  "nameEncrypted": "AES-256 encrypted",
  "nameHash": "HMAC of name",
  "birthdateHash": "HMAC of birthdate"
}
```

**제출 - 규칙 파싱 성공 (type: submission)**

```json
{
  "id": "cohortId_personId_fileHash",
  "cohortId": "safety_2024-2026",
  "type": "submission",
  "personId": "hex",
  "submittedYear": 2025,
  "status": "pending",
  "webpUrl": "https://...",
  "fileHash": "sha256",
  "parsed": {
    "isParsed": true,
    "source": "rule",
    "nameEncrypted": "AES...",
    "year": "2025",
    "organization": "한국안전교육원",
    "serialHash": "HMAC..."
  },
  "adminAction": null,
  "adminCorrection": null
}
```

**제출 - AI 보조 성공 (status = pending_ai)**

```json
{
  "status": "pending_ai",
  "parsed": {
    "source": "gpt-4o-mini",
    ...
  },
  "aiConfidence": 0.92
}
```

**제출 - Unknown (status = unknown)**

```json
{
  "status": "unknown",
  "parsed": {
    "isParsed": false,
    "failedFields": ["name", "serial"]
  }
}
```

### 4.5 admins 컨테이너 문서 예시

```json
{
  "id": "admin@example.com",
  "email": "admin@example.com",
  "type": "super",
  "name": "홍길동"
}
```

**부관리자 (type: sub) 예시**

```json
{
  "id": "subadmin@example.com",
  "email": "subadmin@example.com",
  "type": "sub",
  "name": "김부관",
  "allowedCertificateTypes": ["safety", "health"]
}
```

- `allowedCertificateTypes`: 이 부관리자가 접근할 수 있는 인증서 종류(접두사) 배열. Super 관리자는 모든 종류에 접근 가능하므로 이 필드가 없거나 빈 배열로 처리.

### 4.6 ai_limits 컨테이너 문서

```json
{
  "id": "ratelimit_{fileHash}",
  "partitionKey": "_system",
  "type": "ratelimit",
  "count": 2,
  "expiresAt": "2026-04-09T15:00:00Z",
  "ttl": 3600
}
```

Cosmos DB의 TTL(Time To Live) 기능을 사용하여 자동 삭제. 컨테이너 생성 시 defaultTtl: -1로 설정하고, 각 문서에 ttl: 3600(초)을 지정.

### 4.7 인덱싱 정책 (main 컨테이너)

```json
{
  "indexingMode": "consistent",
  "includedPaths": [ { "path": "/*" } ],
  "excludedPaths": [
    { "path": "/nameEncrypted/*" },
    { "path": "/webpUrl/*" }
  ]
}
```

### 4.8 쿼리 원칙 및 예시

- 컨테이너 내에서 type 필터링으로 구분
- 파티션 키(`/cohortId` 또는 `/email`) 항상 포함

```javascript
// main 컨테이너 쿼리 (파티션 키: cohortId)
const query = `SELECT * FROM c WHERE c.cohortId = @cohortId AND c.type = 'member'`;

// admins 컨테이너 쿼리 (파티션 키: email)
const adminQuery = `SELECT * FROM admins WHERE c.email = @email`;

// ai_limits 컨테이너 (파티션 키: _system)
const limitQuery = `SELECT * FROM ai_limits WHERE c.id = @id`;
```

---

## 5. Express API 구현 명세 (Easy Auth 적용)

### 5.1 기본 구조

```javascript
const express = require('express');
const app = express();
const PORT = process.env.PORT || 80;

// 헬스 체크 (인증 불필요)
app.get('/health', (req, res) => {
  const kstNow = new Date(new Date().toLocaleString('en-US', { timeZone: 'Asia/Seoul' }));
  const hour = kstNow.getHours();
  const minute = kstNow.getMinutes();
  const timeValue = hour * 100 + minute;
  const isBusinessHour = (timeValue >= 830 && timeValue < 1730);
  
  res.status(200).json({
    status: 'ok',
    mode: isBusinessHour ? 'ACTIVE' : 'STANDBY',
    message: isBusinessHour ? '정상 운영 중입니다.' : '현재 업무 시간이 아닙니다. 서비스는 정상 동작하나, 응답이 느릴 수 있습니다.',
    timestamp: new Date().toISOString()
  });
});

// 심층 헬스 체크 (관리자용, 선택)
app.get('/health/deep', async (req, res) => {
  const checks = { cosmos: false, storage: false };
  try {
    await cosmosClient.database('CertificateSystem').container('main').read();
    checks.cosmos = true;
  } catch (e) {}
  try {
    await blobServiceClient.getProperties();
    checks.storage = true;
  } catch (e) {}
  const allHealthy = Object.values(checks).every(v => v);
  res.status(allHealthy ? 200 : 503).json({
    status: allHealthy ? 'ok' : 'degraded',
    checks,
    timestamp: new Date().toISOString()
  });
});

// 관리자 권한 검증 미들웨어 (Easy Auth 헤더 사용)
async function verifyAdmin(req, requiredType, certificateType = null) {
  const email = req.headers['x-ms-client-principal-name'];
  if (!email) throw new Error('Unauthorized');
  
  const container = cosmosClient.database('CertificateSystem').container('admins');
  const { resource: admin } = await container.item(email).read();
  if (!admin) throw new Error('Admin not found');
  
  if (requiredType === 'super' && admin.type !== 'super') {
    throw new Error('Super admin required');
  }
  
  // 부관리자이고, 특정 certificateType이 요청된 경우 접근 권한 확인
  if (admin.type === 'sub' && certificateType) {
    const allowed = admin.allowedCertificateTypes || [];
    if (!allowed.includes(certificateType)) {
      throw new Error(`Access denied to certificate type: ${certificateType}`);
    }
  }
  
  return admin;
}

// 관리자 API 전용 미들웨어 (인증서 종류 추출)
app.use('/api/admin', async (req, res, next) => {
  try {
    // cohortId가 쿼리나 본문에 있는 경우 인증서 종류 추출
    const cohortId = req.query.cohortId || req.body.cohortId;
    const certType = cohortId ? cohortId.split('_')[0] : null;
    req.admin = await verifyAdmin(req, 'sub', certType);
    next();
  } catch (err) {
    res.status(401).json({ error: err.message });
  }
});

// 사용자 API (무인증)
app.post('/api/submit', handleSubmit);
app.post('/api/status', handleStatus);
app.get('/api/view/:cohortId/:personId', handleView);

// 관리자 API (Easy Auth + admins 확인)
app.post('/api/admin/upload-members', handleUploadMembers);
app.post('/api/admin/approve', handleApprove);
app.get('/api/admin/pending', handlePending);
app.post('/api/admin/close-cohort', handleCloseCohort);
app.post('/api/admin/cohorts', handleCreateCohort);
app.post('/api/admin/admins', handleManageAdmins);

app.listen(PORT, () => console.log(`Server running on port ${PORT}`));
```

### 5.2 사용자용 API (무인증)

| 엔드포인트 | 메서드 | 설명 |
|------------|--------|------|
| `/api/submit` | POST | PDF 업로드 → 검증 → 파싱 → AI(필요시) → 변환 → 저장 |
| `/api/status` | POST | `{ name, birthdate }` → personId 계산 → 제출 상태 반환 |
| `/api/view/{cohortId}/{personId}` | GET | 쿼리 name, birthdate로 personId 재계산 후 일치하고 status가 approved일 때만 이미지 스트리밍 |

### 5.3 관리자용 API (Easy Auth + admins)

| 엔드포인트 | 메서드 | 설명 |
|------------|--------|------|
| `/api/admin/pending` | GET | pending/pending_ai/unknown 목록 조회 |
| `/api/admin/approve` | POST | submission 승인/반려, 수정 필드 포함 가능. 행위자는 `req.admin.email` 사용. 낙관적 락 적용 |
| `/api/admin/upload-members` | POST | 엑셀 명단 업로드 → personId 생성 |
| `/api/admin/cohorts` | CRUD | 기수 관리 |
| `/api/admin/admins` | CRUD | 부관리자 관리 (super만 가능) |
| `/api/admin/close-cohort` | POST | 기수 마감: 해당 cohortId의 status='rejected' 문서 일괄 삭제 (민원 대비 3년간 보관 후 삭제) |

**낙관적 락 구현 (이중 클릭 방지):**

```javascript
// handleApprove 함수 내
const { resource: submission } = await container.item(id).read();
if (submission._etag !== req.headers['if-match']) {
  return res.status(409).json({ error: 'Already modified by another request' });
}
// 승인 처리 후
await container.item(id).replace(submission, { ifMatch: submission._etag });
```

**기수 마감 처리 (close-cohort):**

```javascript
async function handleCloseCohort(req, res) {
  const { cohortId } = req.body;
  const query = `SELECT VALUE COUNT(1) FROM c WHERE c.cohortId = @cohortId AND c.type = 'submission' AND c.status = 'rejected'`;
  const [count] = await container.items.query(query, { parameters: [{ name: '@cohortId', value: cohortId }] }).fetchAll();
  
  log('info', 'CLOSE_COHORT', 'About to delete rejected submissions', { cohortId, count, admin: req.admin.email });
  
  const { resources } = await container.items.query(`SELECT * FROM c WHERE c.cohortId = @cohortId AND c.type = 'submission' AND c.status = 'rejected'`).fetchAll();
  for (const doc of resources) {
    await container.item(doc.id, doc.cohortId).delete();
  }
  
  log('info', 'CLOSE_COHORT', 'Deleted rejected submissions', { cohortId, deletedCount: count });
  res.json({ deletedCount: count });
}
```

**관리자 계정 변경 이력 로그:**

```javascript
log('info', 'AUDIT', 'Admin account action', { 
  actor: req.admin.email, 
  action: 'create_admin', 
  targetEmail: newAdmin.email,
  timestamp: new Date().toISOString()
});
```

### 5.4 관리자 승인 시 수정 이력 저장

```json
"adminCorrection": {
  "before": { "name": "김갈동", "year": "2025" },
  "after": { "name": "김길동", "year": "2025" },
  "correctedAt": "2026-04-09T14:35:00Z",
  "correctedBy": "admin@example.com"
}
```

### 5.5 상태 검증 (관리자 실수 방지)

```javascript
const allowedStatuses = ['pending', 'pending_ai', 'unknown'];
if (!allowedStatuses.includes(current.status)) {
  return res.status(400).json({ error: `Cannot approve/reject status '${current.status}'` });
}
```

---

## 6. PDF 검증 로직 (스트림 기반)

모든 PDF 업로드는 다음 검증을 통과해야 한다.

```javascript
const MAX_PDF_SIZE = 10 * 1024 * 1024; // 10MB
const ALLOWED_PDF_VERSION = /^%PDF-1\.[0-7]/;

function validatePdf(buffer) {
  if (buffer.length > MAX_PDF_SIZE) throw new Error('File too large');
  
  // PDF 헤더 검증 (보안 강화)
  const header = buffer.toString('ascii', 0, 8);
  if (!ALLOWED_PDF_VERSION.test(header)) {
    throw new Error('Invalid PDF format or unsupported version');
  }
  
  // 추가: %EOF 존재 여부 확인 (간단한 무결성)
  const tail = buffer.toString('ascii', buffer.length - 20, buffer.length);
  if (!tail.includes('%%EOF')) {
    throw new Error('Incomplete PDF (missing EOF marker)');
  }
  
  return true;
}
```

---

## 7. PDF 인증서 파싱 및 Unknown 처리

### 7.1 규칙 기반 파싱 (pdf-parse)

```javascript
const pdfParse = require('pdf-parse');

async function parseByRule(pdfBuffer, fileHash) {
  const timeoutPromise = new Promise((_, reject) => 
    setTimeout(() => reject(new Error('PDF parse timeout')), 30000)
  );
  
  const data = await Promise.race([pdfParse(pdfBuffer), timeoutPromise]);
  const text = data.text;
  
  // 정규식으로 name, year, organization, serial 추출
  // 실패 시 null 반환
  return { success, parsedData };
}
```

### 7.2 Unknown 처리

- 규칙 파싱 실패 → AI 파이프라인 호출 (8절)
- AI 호출 실패 또는 제한 초과 → status = "unknown", failedFields 기록

---

## 8. AI 보조 인식 파이프라인 (GPT-4o mini Vision)

### 8.1 적용 조건

규칙 기반 파싱 실패 시에만 호출. 정상 문서는 AI를 거치지 않음.

### 8.2 모델 및 비용

- 모델: Azure OpenAI GPT-4o mini (Vision)
- 이미지 전달: WebP 변환 직후, 안전한 이미지 버퍼 전송 (PDF 원본은 이미 파기)
- 비용: 약 $0.005~0.01/건, 연간 30~50건 → $0.15~0.5 (연 $100 크레딧 내)

### 8.3 AI 호출 상한 (Cosmos DB TTL 기반)

```javascript
async function checkAndIncrementAILimit(fileHash) {
  const container = cosmosClient.database('CertificateSystem').container('ai_limits');
  const docId = `ratelimit_${fileHash}`;
  
  try {
    const { resource } = await container.item(docId, '_system').read();
    if (resource && resource.count >= 3) {
      return false; // 제한 초과
    }
    
    const newCount = (resource?.count || 0) + 1;
    await container.upsert({
      id: docId,
      partitionKey: '_system',
      type: 'ratelimit',
      count: newCount,
      ttl: 3600 // 1시간 후 자동 삭제
    });
    return true;
  } catch (err) {
    log('error', 'AI_LIMIT', 'Failed to check limit', { fileHash, error: err.message });
    return true; // 장애 시 일단 허용 (fail open)
  }
}
```

### 8.4 프롬프트 설계

System Prompt:

```
너는 공공/교육 기관의 이수 인증서에서 데이터를 추출하는 전문 AI 비서야.
제공된 인증서 이미지를 분석해서 아래 JSON 형식으로만 응답해.
만약 특정 필드를 도저히 찾을 수 없다면 null로 표기해.

{
  "name": "수강자 성명",
  "year": "이수 연도 (YYYY)",
  "organization": "발급 기관명",
  "serial": "인증서 고유 번호 또는 문서 번호"
}
```

### 8.5 AI 호출 및 결과 저장

```javascript
async function callAI(imageBuffer, fileHash) {
  const response = await openai.chat.completions.create({
    model: "gpt-4o-mini",
    messages: [
      { role: "system", content: systemPrompt },
      { role: "user", content: [{ type: "image_url", image_url: { url: `data:image/webp;base64,${imageBuffer.toString('base64')}` } }] }
    ],
    response_format: { type: "json_object" },
    timeout: 10000 // 10초 타임아웃
  });
  const data = JSON.parse(response.choices[0].message.content);
  const success = data.name && data.year && data.organization && data.serial;
  return { success, data };
}
```

- AI 성공 → status = "pending_ai", parsed.source = "gpt-4o-mini", AI 추천값 저장
- AI 실패 (필드 누락, 타임아웃, API 오류) → status = "unknown", 기존 Unknown 처리

### 8.6 관리자 검수 워크플로우 (Human-in-the-Loop)

1. 알림톡 발송 (status = pending_ai 또는 unknown)
2. SAS URL 접속 (1시간 유효): WebP 이미지 + AI 추천 데이터(또는 빈 칸) 표시
3. 관리자 수정 및 승인
4. 저장 및 피드백

### 8.7 관리자 수정 이력 보존

```json
"adminCorrection": {
  "before": { "name": "김갈동", "year": "2025" },
  "after": { "name": "김길동", "year": "2025" },
  "correctedAt": "2025-03-15T14:35:00Z",
  "correctedBy": "admin@example.com"
}
```

### 8.8 AI 장애 처리

- AI 호출 타임아웃(10초) 또는 API 오류 → status = "unknown" fallback
- 에러 로그: `log('error', 'AI_PARSER', 'Failed', { fileHash, error: err.message })`

### 8.9 재학습 (선택)

- 관리자 승인/반려 데이터를 주기적으로 수집 (매주 또는 100건)
- 프롬프트에 예제 추가 또는 fine-tuning 없이도 컨텍스트 누적으로 성능 향상 가능

---

## 9. PDF → WebP 변환 파이프라인

### 9.1 표준 워크플로우

1. 입력: application/pdf 파일 (메모리 내 버퍼)
2. Ghostscript 렌더링:
   ```bash
   gs -dSAFER -dBATCH -dNOPAUSE -sDEVICE=png16m -r300 -dFirstPage=1 -dLastPage=1 -sOutputFile=output.png input.pdf
   ```
   - 첫 페이지, 300DPI, PNG 포맷
3. Sharp 최적화: PNG 버퍼를 WebP로 변환 (품질 80%)
4. Blob 업로드: WebP 버퍼를 Storage Account `webps` 컨테이너에 업로드 (Managed Identity 사용)

### 9.2 업로드 경로 생성

인증서 종류별로 업로드 위치를 다르게 구성한다.

```javascript
// cohortId에서 접두사 추출 (예: "safety_2024-2026" → "safety")
const certificateType = cohortId.split('_')[0];
const blobName = `${certificateType}/${studentId}/${recordType}/${Date.now()}_${fileName}`;
const blockBlobClient = blobContainer.getBlockBlobClient(blobName);
await blockBlobClient.uploadData(webpBuffer);
```

### 9.3 워밍업 로그

```javascript
const start = Date.now();
// 렌더링
const renderTime = Date.now() - start;
log('info', 'PDF_CONVERT', 'Rendering completed', { fileHash, renderTime_ms: renderTime });
```

### 9.4 오류 로깅

```javascript
log('error', 'PDF_CONVERT_ERROR', 'Rendering failed', { fileHash, error: err.message });
log('error', 'PDF_CONVERT_ERROR', 'Optimization failed', { fileHash, error: err.message });
log('error', 'PDF_CONVERT_ERROR', 'Upload failed', { fileHash, error: err.message });
```

---

## 10. Dockerfile 및 빌드/배포

### 10.1 Dockerfile (비root 사용자 추가)

```dockerfile
FROM node:20-slim

# Ghostscript 및 한글 폰트 설치
RUN apt-get update && \
    apt-get install -y ghostscript fonts-nanum && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Ghostscript 폰트 링크
RUN ln -s /usr/share/fonts/truetype/nanum /usr/share/ghostscript/fonts/

# 비root 사용자 생성 (보안 강화)
RUN groupadd -r appgroup && useradd -r -g appgroup appuser

WORKDIR /app

# 의존성 설치 (소유권 변경)
COPY --chown=appuser:appgroup package*.json ./
RUN npm ci --only=production

# 소스 코드 복사
COPY --chown=appuser:appgroup . .

# 비root 사용자로 전환
USER appuser

EXPOSE 80
CMD ["node", "index.js"]
```

### 10.2 이미지 빌드 및 ACR 푸시

```bash
docker buildx build --platform linux/amd64 -t <acrName>.azurecr.io/records-api:latest --push .
```

### 10.3 Container App 생성 (Azure CLI)

```bash
az containerapp create \
  --name <appName> \
  --resource-group <rgName> \
  --environment <containerEnvName> \
  --image <acrName>.azurecr.io/records-api:latest \
  --min-replicas 0 --max-replicas 2 \
  --scale-rule-name http-rule --scale-rule-type http --scale-rule-http-concurrent 50 \
  --scale-rule-name weekday-up --scale-rule-type cron --scale-rule-cron-schedule "30 8 * * 1-5" --scale-rule-cron-timezone "Asia/Seoul" --scale-rule-cron-desired-replicas 1 \
  --scale-rule-name weekday-down --scale-rule-type cron --scale-rule-cron-schedule "30 17 * * 1-5" --scale-rule-cron-timezone "Asia/Seoul" --scale-rule-cron-desired-replicas 0 \
  --ingress external --target-port 80 \
  --transport auto \
  --enable-auth true \
  --auth-client-id ... --auth-client-secret ...  # Easy Auth 설정
```

---

## 11. 모니터링 및 로깅 (다원화 전략)

### 11.1 데이터 생애주기 및 저장소 전략

| 구분 | 대상 데이터 | 저장소 | 보관 기간 | 핵심 가치 |
|------|-------------|--------|-----------|-----------|
| Audit | 제출 성공, 승인 이력, 명단 수정 | Log Analytics | 기수 종료 후 6년 (총 최대 9년) | 민원 대응 및 행정적 증빙 |
| Debug | 함수 실행 흐름, 단순 상태 값 | Console (stdout) | 7일 | 단기 장애 복구 및 흐름 파악용 (휘발성) |
| Error | 시스템 예외, 보안 위협 시그널 | App Insights | 1년 | 연간 장애 통계 및 시스템 안정성 분석 |
| Metrics | 물리적/성능적 순수 수치 | App Insights | 무기한/장기 | 시스템 성능 변천사 및 인프라 운영 자산 |

### 11.2 구조화 로깅 (JSON 형식)

```javascript
function log(level, category, message, data = {}) {
  const entry = {
    timestamp: new Date().toISOString(),
    level,      // 'info', 'warn', 'error'
    category,   // 'AUDIT', 'PDF_CONVERT', 'AI_PARSER', 'CLOSE_COHORT', etc.
    message,
    ...data
  };
  console.log(JSON.stringify(entry));
}
```

### 11.3 자산형 순수 메트릭 수집 리스트

① 인프라 가용성 자산
- Startup Latency (ms)
- Instance Alive Time (sec)
- CPU/Memory Peak (%)

② 성능 및 물리적 소요 시간
- Phase Duration (ms)
- External API Latency (ms)
- Database RU Usage

③ 용량 및 트래픽 자산
- File Size Metrics (Bytes)
- Egress Data (Bytes)
- Token Usage

④ 비즈니스 건전성 수치
- Concurrent Requests
- AI Confidence Score
- Validation Failure Count

### 11.4 실무 운영 및 자동화 전략

① 로그 통합 스트림 (Single Stream)  
② `/health` 엔드포인트의 지능형 응답  
③ 장애 예측 및 Smart Detection

### 11.5 메트릭 알림 및 정기 보고

- 크리티컬 상황(서비스 5분 이상 중단, 1시간 내 500 에러 10회 이상)에만 알림톡 발송
- 주간/월간/연간 정기 보고서 이메일 전송

### 11.6 비용 통제 안전장치 (Financial Guardrail)

| 서비스 | 일일 상한 | 알림 조건 | 알림 채널 |
|--------|-----------|-----------|-----------|
| Log Analytics (Audit) | 0.4 GB | 80% 도달 | 이메일 (Azure Monitor) |
| Application Insights (Error/Metrics) | 0.1 GB | 80% 도달 | 이메일 (Azure Monitor) |
| 구독 수준 | 연간 $100 예산 | 80%, 100% 초과 | 이메일 (Azure Budget) |

---

## 12. 비용 분석

- 월 $0 (Consumption Plan 무료 할당량 내)

계산 전제:
- 평일 업무 시간(08:30~17:30) 동안만 minReplicas=1 유지
- 주말, 공휴일, 야간에는 minReplicas=0
- 월 평균 가동 시간: 9시간 × 20일 = 180시간
- vCPU 사용량: 0.25 vCPU × 180시간 = 45 vCPU-시간 = 162,000 vCPU-초
- 무료 할당량: 월 180,000 vCPU-초

⚠️ 주의: HTTP 트래픽에 의해 replica가 2개로 확장될 경우, 해당 시간의 vCPU 사용량은 무료 할당량을 초과할 수 있다. 그러나 300명 규모에서 일시적인 확장은 월간 총량에 큰 영향을 주지 않으며, 학생 크레딧 범위 내에서 충분히 수용 가능하다.

---

## 13. 테스트 시나리오

- `/health` 엔드포인트 확인 (업무 시간/비업무 시간/기수 종료 시 응답 검증)
- `/health/deep` 엔드포인트로 종속성 상태 확인
- Easy Auth: 관리자 로그인 후 `/api/admin/pending` 호출 시 200, 무인증 시 401
- PDF 업로드 → 파싱 → AI → 변환 → 저장
- AI 호출 상한 테스트: 동일 파일 4회 연속 업로드 시 3회 이후 AI 호출 차단 확인
- 공휴일 테스트: 공휴일에 서버에 접속하면 콜드 스타트 후 정상 응답 확인
- `/api/status` 응답에 비업무 시간 안내 메시지 포함 확인
- 승인 API 이중 클릭 시 409 충돌 응답 확인 (낙관적 락)
- 기수 마감 API 호출 후 rejected 문서 삭제 및 count 확인
- Dockerfile 비root 사용자로 프로세스 실행 확인 (`ps aux`)
- 부관리자가 허용되지 않은 인증서 종류의 관리자 API 호출 시 401 오류 확인

---

## 14. 문제 해결 가이드

| 문제 | 원인 | 해결 |
|------|------|------|
| Easy Auth 헤더 없음 | 인증 안 됨 | 관리자 API 호출 시 로그인 필요 |
| 관리자 권한 없음 | admins에 없음 | DB에 관리자 이메일 추가 |
| 부관리자 접근 거부 | allowedCertificateTypes에 해당 종류 없음 | Super 관리자가 권한 추가 |
| HTTPS 적용 안 됨 | ACA는 기본 제공 | 설정 확인 |
| replica 확장 비용 우려 | 일시적 트래픽 증가 | 월간 사용량 모니터링, 대부분 무료 할당량 내 |
| 기수 종료 후에도 제출 가능 | active 필드 미사용 | 코드에서 cohort.active=false 체크 로직 추가 |
| 비업무 시간에 응답 지연 | 콜드 스타트 | 정상 동작, 사용자 안내 메시지 표시 |
| 승인 충돌 (409) | 동시 승인 시도 | 낙관적 락으로 방지, 재시도 안내 |
| AI 호출 상한 초과 (429) | 악의적 호출 또는 과도한 Unknown | 일시 제한, 관리자 검토 필요 |
| PDF 파싱 타임아웃 | 복잡한 PDF | 30초 타임아웃 설정, AI fallback |
| 컨테이너 root 실행 | 보안 취약 | Dockerfile에 USER appuser 추가 확인 |

---

## 15. 유지보수 정책

### 15.1 정기 점검 (분기별)

- Cosmos DB RU 사용량 확인
- Blob Storage Lifecycle 정책 확인 (5년)
- Key Vault 키 교체: aes256-key 1년, hmac-key 고정
- Easy Auth: M365 그룹으로 관리자 관리
- 정기 보고서: 주간/월간/연간 자동 생성 및 관리자 전송
- AI 호출 상한 컨테이너 ai_limits 저장 공간 확인 (자동 삭제되므로 크게 문제 안 됨)
- 부관리자 권한(`allowedCertificateTypes`) 정기 감사

### 15.2 모니터링 인프라

- Application Insights: Error 및 Metrics 영구 자산화를 위해 상시 연결 유지 (일일 상한 0.1GB 엄수, 1년 보관)
- Log Analytics: Audit 로그 보관 (기수 종료 후 6년, 총 최대 9년)
- Console 로그: 7일 휘발성 로그 (장애 복구용)

### 15.3 데이터 정리 정책

- 기수 마감 시 status='rejected' submission 문서 일괄 삭제 (민원 대비 3년간 보관 후 삭제)
- 기수 종료 후 6년 경과 시 Archive Tier 데이터 영구 삭제 (자동화)
- 관리자 계정 변경 이력은 Audit 로그로만 남김 (별도 보존)
- ai_limits 컨테이너는 TTL에 의해 자동 정리 (수동 개입 불필요)

---

## 16. 부록

### 16.1 유용한 CLI 명령어

```bash
# Container App 로그 확인
az containerapp logs show --name <appName> --resource-group <rgName>

# Container App 상태 확인
az containerapp show --name <appName> --resource-group <rgName>

# Container App replica 목록
az containerapp replica list --name <appName> --resource-group <rgName>

# Log Analytics 쿼리 예시 (구조화 로그)
AzureDiagnostics
| where Category == "ContainerAppConsoleLogs"
| extend log = parse_json(LogMessage)
| where log.category == "AUDIT"
| project timestamp, log.message, log.adminEmail
```

### 16.2 주요 정책 요약

| 항목 | 정책 |
|------|------|
| 공휴일 처리 | 서비스 정상 동작, 콜드 스타트 발생 |
| 사용자 안내 | 비업무 시간: "현재 업무 시간이 아닙니다. 서비스는 정상 동작하나, 응답이 느릴 수 있습니다." |
| 기수 종료 안내 | "인증서 제출 기간이 종료되었습니다." |
| 알림톡 | 크리티컬 상황(서비스 중단, 500 에러 급증)에만 발송, 1시간 중복 방지 |
| 정기 보고서 | 주간/월간/연간 자동 생성, 이메일 전송 |
| 데이터 보존 | Audit 3년+6년, Debug 7일, Error 1년, Metrics 무기한 |
| 비용 통제 | 일일 상한 + Azure Budget 알림 (이메일) |
| rejected 삭제 | 기수 마감 시 일괄 삭제 (민원 대비 3년 보관) |
| 승인 이중 클릭 | 낙관적 락(_etag)으로 방지 |
| AI 호출 상한 | 동일 파일 해시 기준 1시간 3회 (Cosmos DB TTL) |
| 컨테이너 보안 | 비root 사용자 실행 (appuser) |
| 로깅 형식 | JSON 구조화 로그 |
| 부관리자 권한 | 인증서 종류별 접근 제한 (allowedCertificateTypes) |

---

**버전 7.3-final | 2026-04-11**  
*이 문서는 "부관리자 권한 세분화" 및 "인증서 종류별 업로드 경로 분리" 요구사항을 반영한 최종 설계서입니다.*