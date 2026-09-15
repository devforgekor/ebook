import azure.functions as func
import json
import traceback
from datetime import datetime
from azure.data.tables import TableClient, UpdateMode

from shared.utils.api_utils import (
    success,
    bad_request,
    server_error,
    get_env
)
from shared.utils.auth_utils import require_admin
from shared.utils.generation_utils import get_current_generation
from shared.utils.audit_utils import write_audit_log


ROSTER_TABLE = "Roster"


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        # ✅ 관리자 권한(admin, super-admin)
        admin = require_admin(req)

        body = req.get_json()

        name = body.get("name")
        yymmdd = body.get("yymmdd")
        org = body.get("org", "")
        position = body.get("position", "")

        if not name or not yymmdd:
            return bad_request("name, yymmdd는 필수입니다.")

        conn = get_env("AzureWebJobsStorage")
        roster = TableClient.from_connection_string(conn, table_name=ROSTER_TABLE)

        # ✅ person_id 생성 방식은 DI 제출과 동일
        from shared.utils.id_utils import generate_person_id
        person_id = generate_person_id(name, yymmdd)

        gen = str(get_current_generation())

        # ✅ 기존 사용자 여부 확인
        try:
            roster.get_entity(gen, person_id)
            return bad_request("이미 존재하는 사용자(person_id)입니다.")
        except:
            pass  # 존재하지 않으면 정상 흐름

        # ✅ 신규 사용자 Roster 엔티티 생성
        item = {
            "PartitionKey": gen,
            "RowKey": person_id,
            "name": name,
            "yymmdd": yymmdd,
            "org": org,
            "position": position,
            "status": "incomplete",      # 기본값
            "workstatus": "working",     # 기본값
            "record_keys": json.dumps([]),
            "generation": gen,
            "remark": "",
            "last_updated": datetime.utcnow().isoformat()
        }

        roster.upsert_entity(item, mode=UpdateMode.REPLACE)

        # ✅ audit 기록
        write_audit_log("add_member", {
            "admin_id": admin.get("admin_id"),
            "person_id": person_id,
            "name": name,
            "yymmdd": yymmdd,
            "org": org,
            "position": position
        })

        return success({
            "message": "사용자가 성공적으로 추가되었습니다.",
            "person_id": person_id,
            "generation": gen
        })

    except ValueError as e:
        return bad_request(str(e))
    except Exception as e:
        print("🔥 addMember Error")
        print(traceback.format_exc())
        return server_error(e)
    