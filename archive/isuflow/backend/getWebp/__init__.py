import azure.functions as func
from azure.storage.blob import BlobClient

from shared.utils.api_utils import bad_request, server_error, get_env
from shared.utils.shadowindex_utils import get_blob_path_from_record


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        record_key = req.params.get("record_key")
        if not record_key:
            return bad_request("record_key 파라미터가 필요합니다.")

        blob_path = get_blob_path_from_record(record_key)
        if not blob_path:
            return bad_request("WebP를 찾을 수 없습니다.")

        conn = get_env("AzureWebJobsStorage")
        blob = BlobClient.from_connection_string(conn, "optimized-copies", blob_path)
        data = blob.download_blob().readall()

        return func.HttpResponse(
            body=data,
            mimetype="image/webp",
            status_code=200
        )

    except Exception as e:
        return server_error(e)
    
    