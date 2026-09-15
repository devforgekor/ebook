import azure.functions as func
import pandas as pd
from azure.data.tables import TableClient
from shared.utils.roster_utils import update_roster
from shared.utils.audit_utils import write_audit
from shared.utils.generation_utils import get_generation
import os
import io
import json


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        file = req.files.get("file")
        if not file:
            return func.HttpResponse("Roster file required.", status_code=400)

        # 업로드 파일 CSV/XLSX 자동 판별
        content = file.stream.read()
        df = pd.read_excel(io.BytesIO(content)) if file.filename.endswith("xlsx") else pd.read_csv(io.BytesIO(content))

        # 필수 컬럼 체크
        required = ["name", "yymmdd", "org", "position"]
        for r in required:
            if r not in df.columns:
                return func.HttpResponse(f"Missing required column: {r}", status_code=400)

        conn = os.environ["AzureWebJobsStorage"]
        roster = TableClient.from_connection_string(conn, "Roster")

        # 현재 년도 → generation 계산
        import datetime
        year = datetime.datetime.now().year
        current_gen = get_generation(year)

        # 기존 Roster 로드 (기수별)
        existing = {row["RowKey"]: row for row in roster.query_entities(f"PartitionKey eq '{current_gen}'")}

        # 신규/유지/자동 제외 판정
        seen = set()
        logs = []

        for _, row in df.iterrows():
            person_id = row["person_id"] if "person_id" in row else None
            # person_id 없으면 생성
            from shared.id_utils import generate_person_id
            if not person_id:
                person_id = generate_person_id(row["name"], row["yymmdd"])

            seen.add(person_id)

            roster_entity = {
                "generation": str(current_gen),
                "name": row["name"],
                "yymmdd": row["yymmdd"],
                "org": row["org"],
                "position": row["position"]
            }

            update_roster(person_id, roster_entity, None, None)
            logs.append({"action": "roster_update", "person_id": person_id})

        # 자동 제외 처리 (기존엔 있었는데 이번 명단에 없음)
        for person_id in existing.keys():
            if person_id not in seen:
                entity = existing[person_id]
                entity["status"] = "excluded"
                entity["workstatus"] = "retired"
                roster.upsert_entity(entity)
                logs.append({"action": "auto_excluded", "person_id": person_id})

        # audit 기록
        write_audit("upload_roster", logs)

        return func.HttpResponse("Roster updated successfully.", status_code=200)

    except Exception as e:
        return func.HttpResponse(f"Error: {str(e)}", status_code=500)
    
    