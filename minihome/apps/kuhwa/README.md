# 한국구화학교 학사일정

한국구화학교(서울특별시교육청, 학교코드 7010473)의 학사일정만 보여주는 서버 없는(Vercel 서버리스) 웹사이트입니다.

## 구조

- `public/index.html` — 정적 프론트엔드. `/api/schedule`를 호출해 학사일정을 연도별로 보여줍니다.
- `api/schedule.js` — Vercel 서버리스 함수. NEIS(교육정보 개방 포털) `SchoolSchedule` API를 호출해 한국구화학교의 학사일정을 조회하고, 학교급(초/중/고 등) 중복을 병합해 JSON으로 반환합니다.

## 환경변수

Vercel 프로젝트에 아래 환경변수가 필요합니다.

- `NEIS_API_KEY` — NEIS Open API 인증키

## 로컬 개발

```bash
npm install -g vercel   # 최초 1회
vercel dev
```

## 배포

이 저장소를 Vercel 프로젝트(`prj_TBAJ1w7MsHhxBm51rwbNBYopv1ex`)와 연결하여 배포합니다.

```bash
vercel --prod
```
