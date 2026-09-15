import json
import base64
from azure.functions import HttpRequest
from shared.utils.api_utils import bad_request
from datetime import datetime, timedelta


# ✅ JWT payload 추출 (Authorization: Bearer xxx)
def _decode_jwt_payload(req: HttpRequest):
    auth = req.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        return None

    token = auth.split(" ")[1]

    # JWT 구조: header.payload.signature
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None

        payload_b64 = parts[1] + "==="   # padding
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return payload
    except Exception:
        return None


# ✅ 관리자 역할 기본 규칙
def _ensure_role(payload, allowed_roles):
    role = payload.get("role")
    if role not in allowed_roles:
        return False
    return True


# ✅ 관리자인지 검사 (super-admin 또는 admin)
def require_admin(req: HttpRequest):
    payload = _decode_jwt_payload(req)
    if not payload:
        raise PermissionError("authorization_failed")

    if not _ensure_role(payload, ["super-admin", "admin"]):
        raise PermissionError("permission_denied")

    return payload


# ✅ PDF 조회는 “추가 인증(Elevation)” 필요
#    admin → 반드시 elevation_flag=True 여야 함
def require_admin_pdf_permission(req: HttpRequest):
    payload = _decode_jwt_payload(req)
    if not payload:
        raise PermissionError("authorization_failed")

    role = payload.get("role")
    elevated = payload.get("elevated", False)

    if role == "super-admin":
        return payload

    # admin은 elevation 필요
    if role == "admin" and elevated is True:
        return payload

    raise PermissionError("pdf_permission_denied")


# ✅ Settings 변경 / schedule 변경 = 추가 인증(Elevation) 필수
def require_admin_elevated(req: HttpRequest):
    payload = _decode_jwt_payload(req)
    if not payload:
        raise PermissionError("authorization_failed")

    role = payload.get("role")
    elevated = payload.get("elevated", False)

    # super-admin은 elevation 없이 허용
    if role == "super-admin":
        return payload

    if role == "admin" and elevated is True:
        return payload

    raise PermissionError("elevation_required")

