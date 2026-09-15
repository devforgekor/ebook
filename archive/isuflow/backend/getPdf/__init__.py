import azure.functions as func
from azure.storage.blob import BlobClient

from shared.utils.api_utils import (
    bad_request,
    server_error,
    get_env
)
from shared.utils.auth_utils import require_admin_pdf_permission
from shared.utils.shadowindex_utils import get_pdf_blob_path


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        # ✅ 관리자 권한 + PDF 조회는 추가 인증 필요
        require_admin_pdf_permission(req)

        record_key = req.params.get("record_key")
        if not record_key:
            return bad_request("record_key 파라미터가 필요합니다.")

        # ✅ PDF 파일 경로 조회 (ShadowIndex 기반)
        blob_path = get_pdf_blob_path(record_key)
        if not blob_path:
            return bad_request("PDF 파일을 찾을 수 없습니다.")

        # ✅ 환경변수 안전 로딩
        conn = get_env("AzureWebJobsStorage")

        # ✅ Blob 다운로드
        blob = BlobClient.from_connection_string(
            conn,
            container_name="optimized-copies",
            blob_name=blob_path
        )
        pdf_bytes = blob.download_blob().readall()

        # ✅ PDF 스트리밍 반환
        return func.HttpResponse(
            body=pdf_bytes,
            mimetype="application/pdf",
            status_code=200
        )

    except ValueError as e:
        # ✅ 환경변수 누락 등
        return bad_request(str(e))
    except Exception as e:
        # ✅ 내부 서버 오류 처리
        return server_error(e)
    
    