import hmac
import hashlib
import time
from datetime import datetime


# ✅ 1) 문자열 정규화
# - 공백 제거
# - 소문자 변환
# - unicode normalize 방지 목적의 간단한 normalizer
def _normalize_string(s: str) -> str:
    return s.strip().lower()


# ✅ 2) person_id 생성 규칙 (문서 3.1 / 4.1 정의)
# person_id = HMAC_SHA256( normalize(name) + "_" + yymmdd )[0:16]
def generate_person_id(name: str, yymmdd: str) -> str:
    secret = "ISUFLOW_HMAC_KEY"  # 실제 운영에서는 ENV에서 로드
    base = f"{_normalize_string(name)}_{yymmdd}"

    digest = hmac.new(
        secret.encode("utf-8"),
        base.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    # ✅ 앞 16바이트(32 hex chars)만 사용
    return digest[:32]


# ✅ 3) ssms timestamp 생성 (초 + 밀리초 기반)
# - record_key 뒤에 붙을 유일 값
def _ssms() -> str:
    now = datetime.utcnow()
    epoch_ms = int(now.timestamp() * 1000)
    return str(epoch_ms)


# ✅ 4) record_key 생성 규칙 (문서 3.1 / 4.1)
# record_key = person_id + "_" + ssms()
def generate_record_key(person_id: str) -> str:
    return f"{person_id}_{_ssms()}"


# ✅ 5) 파일명 규칙 생성기
# 운영 중 WebP/PDF:
#   {year}_{person_id}_{record_key}.ext
def build_operational_filename(year: str, person_id: str, record_key: str, ext: str) -> str:
    return f"{year}_{person_id}_{record_key}.{ext}"


# ✅ 6) 아카이브 WebP 파일명
# 아카이브는 record_key 단독 → {record_key}.webp
def build_archive_webp_filename(record_key: str) -> str:
    return f"{record_key}.webp"

