import azure.functions as func
import json
import traceback
from azure.storage.blob import ContainerClient
from azure.data.tables import TableClient

from shared.utils.api_utils import (
    success,
    bad_request,
    server_error,
    get_env
)
from shared.utils.auth_utils import require_admin  # sub-admin도 허용하려면 변경 가능


def _count_blobs(container: ContainerClient, prefix: str = None, ext: str = None):
    count = 0
    blobs = container.list_blobs(name_starts_with=prefix) if prefix else container.list_blobs()
    for b in blobs:
        if ext:
            if b.name.lower().endswith(ext.lower()):
                count += 1
        else:
            count += 1
    return count


def _count_rows(table: TableClient):
    return len(list(table.list_entities()))


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        # ✅ 관리자 권한(admin, super-admin) 확인
        admin = require_admin(req)

        conn = get_env("AzureWebJobsStorage")

        # ✅ Blob Containers
        incoming = ContainerClient.from_connection_string(conn, "incoming")
        optimized = ContainerClient.from_connection_string(conn, "optimized-copies")
        archive_root = ContainerClient.from_connection_string(conn, "archive")

        # ✅ Table Clients
        roster = TableClient.from_connection_string(conn, "Roster")
        shadow = TableClient.from_connection_string(conn, "ShadowIndex")
        unknown = TableClient.from_connection_string(conn, "UnknownLog")
        history = TableClient.from_connection_string(conn, "History")
        settings = TableClient.from_connection_string(conn, "Settings")
        audit = TableClient.from_connection_string(conn, "AuditLog")

        # -------------------------------------------------------------
        # ✅ Blob Storage 분석
        # -------------------------------------------------------------
        incoming_total = _count_blobs(incoming)

        optimized_webp = _count_blobs(optimized, ext=".webp")
        optimized_pdf = _count_blobs(optimized, ext=".pdf")

        # archive/{gen}/ 폴더는 prefix로 판단
        archive_total = _count_blobs(archive_root)

        # WebP / PDF 불일치 quick check
        orphan_suspect = abs(optimized_webp - optimized_pdf)

        # -------------------------------------------------------------
        # ✅ Table Storage 분석
        # -------------------------------------------------------------
        roster_rows = _count_rows(roster)
        shadow_rows = _count_rows(shadow)
        unknown_rows = _count_rows(unknown)
        history_rows = _count_rows(history)
        settings_rows = _count_rows(settings)
        audit_rows = _count_rows(audit)

        # -------------------------------------------------------------
        # ✅ 결과 정리
        # -------------------------------------------------------------
        result = {
            "blob_storage": {
                "incoming": incoming_total,
                "optimized_copies": {
                    "webp_count": optimized_webp,
                    "pdf_count": optimized_pdf,
                    "mismatch_suspect": orphan_suspect
                },
                "archive_total_files": archive_total
            },
            "table_storage": {
                "roster": roster_rows,
                "shadowindex": shadow_rows,
                "unknownlog": unknown_rows,
                "history": history_rows,
                "settings": settings_rows,
                "auditlog": audit_rows
            }
        }

        return success(result)

    except Exception as e:
        return server_error(e)
    
