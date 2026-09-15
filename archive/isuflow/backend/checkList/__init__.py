import azure.functions as func

from shared.utils.api_utils import success, bad_request, server_error
from shared.utils.time_utils import is_open
from shared.utils.person_utils import normalize_and_generate_person_id
from shared.utils.shadowindex_utils import query_shadowindex_by_person


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        if not is_open():
            return bad_request("현재는 제출 시간이 아닙니다.")

        body = req.get_json()
        name = body.get("name")
        yymmdd = body.get("yymmdd")

        if not name or not yymmdd:
            return bad_request("name, yymmdd는 필수입니다.")

        person_id = normalize_and_generate_person_id(name, yymmdd)
        items = query_shadowindex_by_person(person_id)

        if not items:
            return bad_request("제출한 이수증이 없습니다.")

        latest = items[0]
        history = [i.to_history_dict() for i in items[1:]]

        return success({
            "latest_webp_url": f"/api/getWebp?record_key={latest.record_key}",
            "history": history
        })

    except Exception as e:
        return server_error(e)
    
    