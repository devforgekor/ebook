import azure.functions as func
from shared.settings_loader import load_settings
from shared.utils.time_utils import is_open_now
import json

def main(req: func.HttpRequest) -> func.HttpResponse:
    settings = load_settings()

    open_status, msg = is_open_now(settings)

    if open_status:
        return func.HttpResponse(
            json.dumps({"open": True}),
            mimetype="application/json",
            status_code=200
        )
    else:
        return func.HttpResponse(
            json.dumps({"open": False, "message": msg}),
            mimetype="application/json",
            status_code=200
        )
    
    