import azure.functions as func
import json
import traceback
from azure.storage.blob import ContainerClient, BlobClient
from azure.data.tables import TableClient

from shared.utils.api_utils import (
    success,
    bad_request,
    server_error,
    get_env
)
from shared.utils.auth_utils import require_admin
from shared.utils.audit_utils import write_audit_log
from shared.utils.pdf_utils import pdf_first_page_to_image
from shared.utils.image_utils import upload_webp_optimized
from shared.utils.shadowindex_utils import get_shadow_row


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        # ✅ 관리자만 가능
        admin = require_admin(req)

        conn = get_env("AzureWebJobsStorage")
        optimized = ContainerClient.from_connection_string(conn, "optimized-copies")
        table = TableClient.from_connection_string(conn, table_name="ShadowIndex")

        # -------------------------------------------------------
        # ✅ 1. 모든 ShadowIndex row 읽기
        # -------------------------------------------------------
        shadow_rows = list(table.list_entities())
        shadow_keys = {r["RowKey"]: r for r in shadow_rows}

        # -------------------------------------------------------
        # ✅ 2. optimized-copies에 존재하는 모든 파일 읽기
        # -------------------------------------------------------
        blobs = list(optimized.list_blobs())
        blob_names = [b.name for b in blobs]

        # record_key 추출 (파일명 = {year}_{person_id}_{record_key}.ext)
        def extract_record_key(name):
            parts = name.split(".")[0].split("_")
            if len(parts) < 3:
                return None
            return parts[-1]

        # -------------------------------------------------------
        # ✅ 결과 저장용
        # -------------------------------------------------------
        orphan_webp = []         # 파일은 있는데 ShadowIndex 없음 → 삭제
        orphan_record = []       # ShadowIndex엔 있는데 파일 없음 → 복구 or 제거
        fixed = []               # 실제 조치 내역

        # -------------------------------------------------------
        # ✅ 3. orphan_webp 탐지
        # -------------------------------------------------------
        for b in blob_names:
            if not (b.endswith(".webp") or b.endswith(".pdf")):
                continue

            record_key = extract_record_key(b)
            if not record_key:
                continue

            if record_key not in shadow_keys:
                orphan_webp.append(b)

        # -------------------------------------------------------
        # ✅ orphan_webp 삭제
        # -------------------------------------------------------
        for b in orphan_webp:
            try:
                blob = optimized.get_blob_client(b)
                blob.delete_blob()
                fixed.append({"type": "orphan_webp_deleted", "file": b})
            except Exception as e:
                fixed.append({"type": "orphan_webp_delete_failed", "file": b, "error": str(e)})

        # -------------------------------------------------------
        # ✅ 4. orphan_record 탐지
        # -------------------------------------------------------
        for record_key, row in shadow_keys.items():
            webp_name = f"{row['year']}_{row['person_id']}_{record_key}.webp"
            pdf_name = f"{row['year']}_{row['person_id']}_{record_key}.pdf"

            has_webp = webp_name in blob_names
            has_pdf = pdf_name in blob_names

            if not has_webp or not has_pdf:
                orphan_record.append({
                    "record_key": record_key,
                    "webp": has_webp,
                    "pdf": has_pdf,
                    "row": row
                })

        # -------------------------------------------------------
        # ✅ orphan_record 처리
        # -------------------------------------------------------
        for item in orphan_record:
            record_key = item["record_key"]
            row = item["row"]

            year = row["year"]
            person_id = row["person_id"]

            pdf_name = f"{year}_{person_id}_{record_key}.pdf"
            webp_name = f"{year}_{person_id}_{record_key}.webp"

            pdf_blob = optimized.get_blob_client(pdf_name)
            webp_blob = optimized.get_blob_client(webp_name)

            # ✅ PDF가 존재하면 WebP 재생성 가능
            if item["pdf"]:
                try:
                    pdf_bytes = pdf_blob.download_blob().readall()
                    img = pdf_first_page_to_image(pdf_bytes)
                    upload_webp_optimized(webp_blob, img)

                    fixed.append({
                        "type": "orphan_record_webp_recreated",
                        "record_key": record_key
                    })
                    continue

                except Exception as e:
                    fixed.append({
                        "type": "orphan_record_webp_recreate_failed",
                        "record_key": record_key,
                        "error": str(e)
                    })

            # ✅ PDF마저 없다면 → ShadowIndex row 삭제
            try:
                table.delete_entity(row["PartitionKey"], row["RowKey"])
                fixed.append({
                    "type": "orphan_record_deleted_shadowindex",
                    "record_key": record_key
                })
            except Exception as e:
                fixed.append({
                    "type": "orphan_record_delete_failed",
                    "record_key": record_key,
                    "error": str(e)
                })

        # -------------------------------------------------------
        # ✅ audit 기록
        # -------------------------------------------------------
        write_audit_log("orphan_cleaner", {
            "admin_id": admin.get("admin_id"),
            "orphan_webp": orphan_webp,
            "orphan_record": [o["record_key"] for o in orphan_record],
            "fixed": fixed
        })

        return success({
            "orphan_webp": orphan_webp,
            "orphan_record": orphan_record,
            "fixed": fixed
        })

    except Exception as e:
        return server_error(e)
    
    