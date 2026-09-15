import azure.functions as func

from shared.utils.api_utils import (
    success,
    bad_request,
    server_error,
    get_env
)
from shared.utils.auth_utils import require_admin
from shared.utils.audit_utils import query_audit_log


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        require_admin(req)

        generation = req.params.get("generation")
        if not generation:
            return bad_request("generation 파라미터가 필요합니다.")

        conn = get_env("AzureWebJobsStorage")

        logs = query_audit_log(conn, generation)

        return success({"logs": logs})

    except Exception as e:
        return server_error(e)
    
    