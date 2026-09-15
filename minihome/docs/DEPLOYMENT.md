# Vercel 배포 설정

## 구조

```
minihome/                         ← Git Repo Root (Minipark-KOR/minihome)
├── apps/
│   ├── minihome/                 ← Vercel Project: minihome (prj_scmMBu4sSrO1DesyKLO38es39sob)
│   │   ├── app/
│   │   │   ├── page.tsx         ← 랜딩 페이지 (프로젝트 링크)
│   │   │   ├── layout.tsx
│   │   │   └── globals.css
│   │   ├── package.json
│   │   ├── next.config.ts
│   │   ├── tsconfig.json
│   │   └── vercel.json
│   ├── news/web/                 ← Vercel Project: news (prj_jDsE3OdG5ajEUTmgGMNKR5bW20yV)
│   ├── cashbook/frontend/        ← Vercel Project: mini-cashbook (prj_QBezAF62BvVw4YA70I3mVIL6zEZw)
│   ├── timetable/                ← Vercel Project: mini-timetable (prj_rvPCSamTzjTeOL1iaP2KW3KYN7cH)
│   └── kuhwa/                    ← Vercel Project: kuhwa (prj_TBAJ1w7MsHhxBm51rwbNBYopv1ex)
├── .gitignore
└── README.md
```

> **ebook (miniebook)**는 별도 저장소 `ebooklib/`에서 관리. 이 모노레포에 포함되지 않음.

## 프로젝트 매핑

| Vercel 프로젝트 | Project ID | 저장소 | Root Directory | Framework |
|----------------|-----------|--------|---------------|-----------|
| **minihome** | `prj_scmMBu4sSrO1DesyKLO38es39sob` | minihome | `apps/minihome/` | Next.js |
| **miniebook** | `prj_AgCf0ZgzOUJ72pn0g9sJvq3lCm9v` | **ebooklib** | `apps/frontend` | Next.js |
| news | `prj_jDsE3OdG5ajEUTmgGMNKR5bW20yV` | minihome | `apps/news/web` | Next.js |
| mini-cashbook | `prj_QBezAF62BvVw4YA70I3mVIL6zEZw` | minihome | `apps/cashbook/frontend` | Static SPA |
| mini-timetable | `prj_rvPCSamTzjTeOL1iaP2KW3KYN7cH` | minihome | `apps/timetable` | Python |
| kuhwa | `prj_TBAJ1w7MsHhxBm51rwbNBYopv1ex` | minihome | `apps/kuhwa` | Next.js Static |

## 서버 구성 비교

| 프로젝트 | vercel.json | 상태 |
|---------|------------|------|
| minihome | `framework: nextjs` | ✅ 표준 |
| news | `framework: nextjs`, `regions: [hnd1]` | ⚠️ hnd1 (도쿄) — 한국 서비스에는 `icn` (서울) 권장 |
| mini-cashbook | rewrites/headers (no framework) | ❌ `framework` 미지정 |
| mini-timetable | `@vercel/python` (main.py) | ❌ Python 서버리스 |
| kuhwa | `version: 2`, rewrites | ⚠️ `version: 2` 구버전 |

## Root Directory 설정 방법 (Vercel 대시보드)

1. Vercel 대시보드 → New Project → Import Git Repository
2. `Minipark-KOR/minihome` 선택
3. **Root Directory** 설정: 각 프로젝트별 디렉토리 지정
4. Deploy

## 주의사항

- 모든 프로젝트는 `apps/` 하위에 배치 (업계 표준)
- minihome과 miniebook은 완전히 별개 프로젝트 (별도 Root Directory)
- 환경변수 (NEXT_PUBLIC_API_URL, NEIS_API_KEY 등)는 Vercel 대시보드에서 별도 설정
- `.env` 파일은 git에 포함되지 않음
