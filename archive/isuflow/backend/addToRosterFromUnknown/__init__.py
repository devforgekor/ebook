import azure.functions as func

from shared.utils.api_utils import (
    success,
    bad_request,
    server_error,
    get_env
)
from shared.utils.auth_utils import require_admin
from shared.utils.roster_utils import promote_unknown_to_roster


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        require_admin(req)

        body = req.get_json()
        record_key = body.get("record_key")
        if not record_key:
            return bad_request("record_key는 필수입니다.")

        conn = get_env("AzureWebJobsStorage")

        result = promote_unknown_to_roster(conn, record_key)

        return success(result)

    except Exception as e:
        return server_error(e)
    