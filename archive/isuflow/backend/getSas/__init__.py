import azure.functions as func
from datetime import datetime, timedelta
from azure.storage.blob import generate_blob_sas, BlobSasPermissions

from shared.utils.api_utils import (
    success,
    bad_request,
    server_error,
    get_env
)
from shared.utils.time_utils import is_open


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        # ✅ 운영시간 체크
        if not is_open():
            return bad_request("현재는 제출 시간이 아닙니다.")

        filename = req.params.get("file")
        if not filename:
            return bad_request("file 파라미터가 필요합니다.")

        account = get_env("STORAGE_ACCOUNT_NAME")
        key = get_env("STORAGE_ACCOUNT_KEY")

        container = "incoming"
        blob_name = f"{filename}.pdf"

        sas = generate_blob_sas(
            account_name=account,
            container_name=container,
            blob_name=blob_name,
            permission=BlobSasPermissions(write=True),
            expiry=datetime.utcnow() + timedelta(minutes=10),
            account_key=key
        )

        url = f"https://{account}.blob.core.windows.net/{container}/{blob_name}?{sas}"
        return success({"url": url})

    except ValueError as e:
        return bad_request(str(e))
    except Exception as e:
        return server_error(e)
    
    