import azure.functions as func

from shared.utils.api_utils import (
    success,
    bad_request,
    server_error,
    get_env
)
from shared.utils.auth_utils import require_admin
from shared.utils.shadowindex_utils import rebuild_shadowindex_full


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        # ✅ 관리자 권한 (추가 인증 필요 없음)
        require_admin(req)

        conn = get_env("AzureWebJobsStorage")

        count = rebuild_shadowindex_full(conn)

        return success({
            "message": f"ShadowIndex 전체 재생성 완료",
            "rows": count
        })

    except Exception as e:
        return server_error(e)
    
    