import azure.functions as func
import json
import traceback
from azure.storage.blob import BlobClient
from azure.storage.queue import QueueClient

from shared.utils.api_utils import (
    success,
    bad_request,
    server_error,
    get_env
)
from shared.utils.auth_utils import require_admin
from shared.utils.audit_utils import write_audit_log


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        # ✅ 관리자 권한 확인
        admin = require_admin(req)

        body = req.get_json()
        files = body.get("files")
        if not files or not isinstance(files, list):
            return bad_request("files 배열이 필요합니다. 예: { 'files': ['url1', 'url2', ...'] }")

        conn = get_env("AzureWebJobsStorage")
        storage_name = get_env("STORAGE_ACCOUNT_NAME")

        queue = QueueClient.from_connection_string(conn, "processpdf")

        incoming_container = "incoming"

        uploaded = 0
        queued = 0
        errors = []

        for file_url in files:
            try:
                # 파일명 추출
                filename = file_url.split("/")[-1]
                if not filename.lower().endswith(".pdf"):
                    errors.append({"file": file_url, "error": "PDF 파일이 아닙니다."})
                    continue

                # ✅ incoming 에 blob 업로드
                incoming_blob = BlobClient.from_connection_string(
                    conn,
                    container_name=incoming_container,
                    blob_name=filename
                )

                # 외부 URL → 다운로드
                import urllib.request
                pdf_bytes = urllib.request.urlopen(file_url).read()

                incoming_blob.upload_blob(pdf_bytes, overwrite=True)
                uploaded += 1

                # ✅ Queue 메시지 생성
                queue_msg = {
                    "pdf_path": filename,
                    "bulk": True
                }
                queue.send_message(json.dumps(queue_msg))
                queued += 1

            except Exception as e:
                print("[BulkUpload Error] file:", file_url)
                print(traceback.format_exc())
                errors.append({"file": file_url, "error": str(e)})

        # ✅ Audit 기록
        write_audit_log("bulk_upload", {
            "admin_id": admin.get("admin_id"),
            "total": len(files),
            "uploaded": uploaded,
            "queued": queued,
            "errors": errors
        })

        return success({
            "total": len(files),
            "uploaded": uploaded,
            "queued": queued,
            "errors": errors
        })

    except Exception as e:
        return server_error(e)
    