import azure.functions as func
import json
import traceback
from azure.data.tables import TableClient

from shared.utils.api_utils import (
    success,
    bad_request,
    server_error,
    get_env
)
from shared.utils.id_utils import generate_person_id


HISTORY_TABLE = "History"


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        conn = get_env("AzureWebJobsStorage")
        table = TableClient.from_connection_string(conn, table_name=HISTORY_TABLE)

        # ✅ Query Parameters
        name = req.params.get("name")
        yymmdd = req.params.get("yymmdd")
        person_id = req.params.get("person_id")
        record_key = req.params.get("record_key")

        # ---------------------------------------------------------
        # ✅ 1) record_key 기반 단일 조회
        # ---------------------------------------------------------
        if record_key:
            rows = list(table.query_entities(f"RowKey eq '{record_key}'"))
            if not rows:
                return bad_request("해당 record_key의 제출 이력이 없습니다.")
            row = rows[0]

            return success({
                "record_key": record_key,
                "submitted_at": row.get("submitted_at"),
                "title": row.get("title"),
                "hours": row.get("hours")
            })

        # ---------------------------------------------------------
        # ✅ 2) person_id 기반 전체 조회
        # ---------------------------------------------------------
        # person_id 미제공 시, name+yymmdd 로 생성
        if not person_id:
            if not name or not yymmdd:
                return bad_request("이력 조회는 record_key 또는 (name + yymmdd)가 필요합니다.")
            person_id = generate_person_id(name, yymmdd)

        rows = list(table.query_entities(f"PartitionKey eq '{person_id}'"))
        rows_sorted = sorted(rows, key=lambda r: r["submitted_at"], reverse=True)

        # ShadowIndex와 동일 형식으로 변환
        history_list = []
        for r in rows_sorted:
            history_list.append({
                "record_key": r["RowKey"],
                "submitted_at": r.get("submitted_at"),
                "title": r.get("title"),
                "hours": r.get("hours")
            })

        return success({
            "person_id": person_id,
            "history": history_list
        })

    except ValueError as e:
        return bad_request(str(e))
    except Exception as e:
        print("🔥 History API Error")
        print(traceback.format_exc())
        return server_error(e)
    
    