import azure.functions as func

from shared.utils.api_utils import (
    success,
    bad_request,
    server_error,
    get_env
)
from shared.utils.auth_utils import require_admin
from shared.utils.shadowindex_utils import list_all_submissions


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        require_admin(req)

        conn = get_env("AzureWebJobsStorage")
        rows = list_all_submissions(conn)

        return success({"submissions": rows})

    except Exception as e:
        return server_error(e)
    
    