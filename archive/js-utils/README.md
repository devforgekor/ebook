# js-utils

`kuhwa`(한국구화학교 학사일정 서비스) 개발 과정에서 만들어진, NEIS나 학사일정과
무관하게 재사용 가능한 Node.js 유틸리티 5종을 뽑아 모아둔 패키지입니다.
`kuhwa` 자체는 수정하지 않았으며, 다음 프로젝트에서 바로 가져다 쓸 수 있도록
`common-lib/harvest/js-utils`에 보관합니다.

## 모듈

| 모듈 | 함수 | 용도 |
|---|---|---|
| `lib/paginate.js` | `fetchAllPages(fetchPage, pageSize)` | 페이지네이션 API: 1페이지로 전체 건수 파악 후 나머지 페이지를 병렬로 수집 |
| `lib/mergeByKey.js` | `mergeByKey(rows, keyFn, mapFn, options)` | 키 기준 중복 병합, 부가 필드는 배열로 누적 |
| `lib/staticFirstFetch.js` | `staticFirstFetch(filePath, fetchRemote, pickFn)`, `readStaticJson(filePath, pickFn)` | 정적 JSON 파일을 우선 읽고, 없을 때만 원격 호출로 폴백 |
| `lib/mailNotifier.js` | `sendFailureMail({ subject, text, config })` | SMTP 환경변수 기반 실패 알림 메일 발송 (예외를 던지지 않음) |
| `lib/validateQueryParam.js` | `validatePattern(res, value, pattern, errorMessage)` | 요청 쿼리 파라미터를 정규식으로 검증, 실패 시 400 응답 |

## 사용 예

```js
const { fetchAllPages, mergeByKey, staticFirstFetch, sendFailureMail, validatePattern } = require("js-utils");

// 1) 페이지네이션 수집
const rows = await fetchAllPages(
  async (pIndex) => {
    const res = await fetch(`https://example.com/api?page=${pIndex}`);
    const data = await res.json();
    return { totalCount: data.total, rows: data.items };
  },
  100 // pageSize
);

// 2) 중복 병합 (키+부가필드 누적)
const events = mergeByKey(
  rows,
  (row) => `${row.date}_${row.name}`,
  (row) => ({ date: row.date, name: row.name, tags: [row.tag].filter(Boolean) }),
  { accumulateField: "tags", accumulateFn: (row) => row.tag }
);

// 3) 정적 파일 우선, 원격 폴백
const data = await staticFirstFetch(
  "/path/to/cache/2026.json",
  () => fetchFromRemoteApi(2026),
  (json) => json.events
);

// 4) 실패 메일 알림 (SMTP_HOST/PORT/USER/PASSWORD, MAIL_TO 환경변수 사용)
await sendFailureMail({ subject: "[batch] 실패", text: String(err) });

// 5) 쿼리 파라미터 검증 (Vercel/Express 핸들러 안에서)
if (!validatePattern(res, req.query.year, /^\d{4}$/, "year는 4자리 숫자여야 합니다.")) return;
```

## 원본 출처

`~/workspace/kuhwa`(현재 `/opt/workspace/kuhwa`)의 `api/schedule.js`,
`api/calendar.js`, `scripts/fetch-schedule.js`에서 NEIS/학사일정 관련 로직을 걷어내고
범용 로직만 남긴 것입니다. `kuhwa` 코드 자체는 이번 작업으로 수정되지 않았습니다.
