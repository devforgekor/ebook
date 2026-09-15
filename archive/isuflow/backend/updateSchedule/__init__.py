import azure.functions as func

from shared.utils.api_utils import (
    success,
    bad_request,
    server_error,
    get_env
)
from shared.utils.auth_utils import require_admin_elevated
from shared.utils.schedule_utils import rebuild_off_schedule


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        # ✅ Settings 변경 = 관리자 + 추가 인증 필요
        require_admin_elevated(req)

        body = req.get_json()
        if not body:
            return bad_request("스케줄 입력값이 없습니다.")

        conn = get_env("AzureWebJobsStorage")

        # ✅ OFF_SCHEDULE 재생성
        off_schedule = rebuild_off_schedule(conn, body)

        return success({
            "off_schedule": off_schedule,
            "message": "운영 일정이 성공적으로 업데이트되었습니다."
        })

    except ValueError as e:
        return bad_request(str(e))
    except Exception as e:
        return server_error(e)
    
    