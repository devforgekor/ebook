import azure.functions as func
from azure.storage.blob import BlobClient
from datetime import datetime
import json
import traceback

from shared.utils.api_utils import get_env, server_error
from shared.utils.pdf_utils import (
    pdf_first_page_to_image,
    insert_pdf_metadata,
    validate_pdf_safety
)
from shared.utils.image_utils import upload_webp_optimized
from shared.utils.id_utils import generate_person_id, generate_record_key
from shared.utils.shadowindex_utils import (
    remove_old_shadowindex_rows,
    insert_shadowindex_row
)
from shared.utils.roster_utils import (
    update_roster_after_submission,
    write_history
)
from shared.utils.tag_utils import set_blob_tags_optimized


def main(msg: func.QueueMessage):
    try:
        event = msg.get_json()

        # ✅ 필수 값
        pdf_path = event["pdf_path"]                # incoming/{file}.pdf
        di = event["di"]                            # DI 결과: name, yymmdd, title, hours, org

        # ✅ 환경변수 안전 로딩
        conn = get_env("AzureWebJobsStorage")
        storage_acct = get_env("STORAGE_ACCOUNT_NAME")

        # ✅ 1) incoming PDF 다운로드
        incoming_blob = BlobClient.from_connection_string(
            conn,
            container_name="incoming",
            blob_name=pdf_path
        )
        pdf_bytes = incoming_blob.download_blob().readall()

        # ✅ 2) PDF 안전성 검사 (악성코드/MIME/JS 삽입)
        validate_pdf_safety(pdf_bytes)

        # ✅ 3) person_id / record_key 생성
        name = di["name"]
        yymmdd = di["yymmdd"]
        person_id = generate_person_id(name, yymmdd)
        record_key = generate_record_key(person_id)
        year = str(datetime.now().year)

        # ✅ 4) PDF 내부 메타데이터 삽입 (비식별)
        pdf_bytes = insert_pdf_metadata(pdf_bytes, person_id, record_key)

        # ✅ 5) 1페이지 → WebP 컬러 변환
        image = pdf_first_page_to_image(pdf_bytes)

        optimized_webp_name = f"{year}_{person_id}_{record_key}.webp"
        optimized_pdf_name = f"{year}_{person_id}_{record_key}.pdf"

        # ✅ 6) 저장 경로 설정
        webp_blob = BlobClient.from_connection_string(
            conn,
            container_name="optimized-copies",
            blob_name=optimized_webp_name
        )
        pdf_blob = BlobClient.from_connection_string(
            conn,
            container_name="optimized-copies",
            blob_name=optimized_pdf_name
        )

        # ✅ 7) WebP 업로드 (최적화 설정)
        upload_webp_optimized(webp_blob, image)

        # ✅ 8) PDF 업로드
        pdf_blob.upload_blob(pdf_bytes, overwrite=True)

        # ✅ 9) Blob Tags 생성 (총 9개)
        set_blob_tags_optimized(pdf_blob, {
            "lookup_key": person_id,
            "person_id": person_id,
            "record_key": record_key,
            "year": year,
            "hours": di["hours"],
            "org_key": di["org"],
            "position_key": di["position"],
            "title_key": di["title"],
            "cert_number": record_key
        })
        set_blob_tags_optimized(webp_blob, {
            "lookup_key": person_id,
            "person_id": person_id,
            "record_key": record_key,
            "year": year,
            "hours": di["hours"],
            "org_key": di["org"],
            "position_key": di["position"],
            "title_key": di["title"],
            "cert_number": record_key
        })

        # ✅ 10) ShadowIndex: 기존 record_key 삭제 → 최신 1건만 유지
        remove_old_shadowindex_rows(person_id)

        insert_shadowindex_row({
            "PartitionKey": person_id,
            "RowKey": record_key,
            "year": year,
            "title_key": di["title"],
            "hours": di["hours"],
            "org_key": di["org"],
            "person_id": person_id,
            "blob_path": optimized_webp_name,
            "cert_number": record_key
        })

        # ✅ 11) Roster 업데이트 (status=completed, record_keys 갱신)
        update_roster_after_submission(
            person_id=person_id,
            di=di,
            record_key=record_key,
            year=year
        )

        # ✅ 12) History JSONL 저장
        write_history(
            person_id=person_id,
            record_key=record_key,
            title=di["title"],
            hours=di["hours"]
        )

        # ✅ 13) incoming PDF 삭제
        incoming_blob.delete_blob()

        print(f"[OK] processPdf 완료: {pdf_path} → {optimized_webp_name}")

    except Exception as e:
        # ✅ Azure Functions 로그에 남김
        print("🔥 processPdf 내부 오류:")
        print(traceback.format_exc())

        # ✅ server_error는 log 출력 + JSON response 형식이지만,
        # Queue Worker는 HTTP가 아니므로 raise 유지
        server_error(e)
        raise e  # 재시도 위해 다시 던짐
    
