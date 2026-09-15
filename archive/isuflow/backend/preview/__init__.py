import azure.functions as func
from azure.storage.blob import BlobClient, BlobSasPermissions, generate_blob_sas
from datetime import datetime, timedelta

from shared.utils.api_utils import success, bad_request, server_error, get_env
from shared.utils.time_utils import is_open
from shared.utils.pdf_utils import pdf_first_page_to_image
from shared.utils.image_utils import upload_temp_webp


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        if not is_open():
            return bad_request("현재는 제출 시간이 아닙니다.")

        file = req.params.get("file")
        if not file:
            return bad_request("file 파라미터가 필요합니다.")

        conn = get_env("AzureWebJobsStorage")

        blob = BlobClient.from_connection_string(
            conn, "incoming", f"{file}.pdf"
        )
        pdf_bytes = blob.download_blob().readall()

        img = pdf_first_page_to_image(pdf_bytes)
        temp_name = f"preview_{file}.webp"

        temp_blob = BlobClient.from_connection_string(
            conn, "temp", temp_name
        )
        upload_temp_webp(temp_blob, img)

        sas = generate_blob_sas(
            account_name=get_env("STORAGE_ACCOUNT_NAME"),
            container_name="temp",
            blob_name=temp_name,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.utcnow() + timedelta(minutes=10),
            account_key=get_env("STORAGE_ACCOUNT_KEY")
        )

        url = f"https://{get_env('STORAGE_ACCOUNT_NAME')}.blob.core.windows.net/temp/{temp_name}?{sas}"
        return success({"url": url})

    except ValueError as e:
        return bad_request(str(e))
    except Exception as e:
        return server_error(e)
    
    