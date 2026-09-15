# mini home — Umbrella Repo

독립적인 웹 프로젝트들을 하나의 저장소로 관리합니다.

## 구조

```
minihome/                         ← Git Repo Root
├── apps/                         ← 이 저장소의 프로젝트들
│   ├── minihome/                 ← Vercel: minihome (prj_scmMBu4sSrO1DesyKLO38es39sob)
│   │   └── app/                  ← 랜딩 페이지 (프로젝트 링크)
│   ├── news/web/               ← Vercel: news (prj_jDsE3OdG5ajEUTmgGMNKR5bW20yV)
│   ├── cashbook/frontend/      ← Vercel: mini-cashbook (prj_QBezAF62BvVw4YA70I3mVIL6zEZw)
│   ├── timetable/              ← Vercel: mini-timetable (prj_rvPCSamTzjTeOL1ia2KW3KYN7cH)
│   ├── kuhwa/                  ← Vercel: kuhwa (prj_TBAJ1w7MsHhxBm51rwbNBYopv1ex)
│   └── ebooklib/               ← Vercel: miniebook (prj_AgCf0ZgzOUJ72pn0g9sJvq3lCm9v)
├── .gitignore
└── README.md
```

## 프로젝트별 배포

| Vercel 프로젝트 | Project ID | 저장소 | Root Directory | Framework |
|----------------|-----------|--------|---------------|-----------|
| minihome | `prj_scmMBu4sSrO1DesyKLO38es39sob` | minihome | `apps/minihome/` | Next.js |
| miniebook | `prj_AgCf0ZgzOUJ72pn0g9sJvq3lCm9v` | **ebooklib** | `apps/frontend` | Next.js |
| news | `prj_jDsE3OdG5ajEUTmgGMNKR5bW20yV` | minihome | `apps/news/web` | Next.js |
| mini-cashbook | `prj_QBezAF62BvVw4YA70I3mVIL6zEZw` | minihome | `apps/cashbook/frontend` | Static SPA |
| mini-timetable | `prj_rvPCSamTzjTeOL1iaP2KW3KYN7cH` | minihome | `apps/timetable` | Python |
| kuhwa | `prj_TBAJ1w7MsHhxBm51rwbNBYopv1ex` | minihome | `apps/kuhwa` | Next.js Static |

## 프로젝트 독립성

각 프로젝트는 완전히 독립적으로 동작합니다:
- 독립적인 디렉토리 구조
- 독립적인 빌드/배포 파이프라인
- 독립적인 의존성 관리
- 독립적인 런타임 환경

## 공유 로직

**공유되는 코드 없음.** 각 앱이 완전히 독립입니다:
- 공통 `lib/`, `config.py`, `logger.py` 없음
- `common-lib/` 미사용
- FastAPI 3개 앱 (cashbook, timetable, ebooklib) — 독립 구조
- Next.js 2개 앱 (kuhwa, minihome) — 독립 구조

## 공통 규칙

- 모든 프로젝트는 `apps/` 하위에 배치 (업계 표준)
- 루트 레벨에는 프로젝트 코드 없음 (설정 파일만)
- 각 프로젝트의 README를 참고하여 개별 운영
