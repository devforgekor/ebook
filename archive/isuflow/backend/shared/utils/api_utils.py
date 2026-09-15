import json
import traceback
import os
import azure.functions as func


# ✅ 환경변수 안전하게 읽는 함수
def get_env(key: str, required: bool = True):
    val = os.environ.get(key)
    if required and not val:
        raise ValueError(f"환경변수 '{key}'이(가) 설정되지 않았습니다.")
    return val


# ✅ 통일된 성공 응답
def success(data=None):
    return func.HttpResponse(
        json.dumps({"success": True, "data": data}, ensure_ascii=False),
        mimetype="application/json",
        status_code=200
    )


# ✅ 사용자 잘못 (400)
def bad_request(message: str):
    return func.HttpResponse(
        json.dumps({"success": False, "error": message}, ensure_ascii=False),
        mimetype="application/json",
        status_code=400
    )


# ✅ 내부 서버 오류 (500)
def server_error(e: Exception):
    print("🔥 내부 오류 발생:")
    print(traceback.format_exc())

    return func.HttpResponse(
        json.dumps({
            "success": False,
            "error": "internal_error",
            "message": str(e)
        }, ensure_ascii=False),
        mimetype="application/json",
        status_code=500
    )

