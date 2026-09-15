import azure.functions as func
import json
import traceback
from azure.storage.queue import QueueClient
from datetime import datetime

from shared.utils.api_utils import (
    success,
    bad_request,
    server_error,
    get_env
)
from shared.utils.auth_utils import require_admin


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        # ✅ 관리자 권한 확인 (admin, super-admin)
        admin = require_admin(req)

        conn = get_env("AzureWebJobsStorage")
        queue_name = "processpdf"

        queue = QueueClient.from_connection_string(conn, queue_name)

        # ✅ Queue 속성 조회
        props = queue.get_queue_properties()
        approx = props.approximate_message_count

        # ✅ 최초 및 마지막 메시지 확인
        messages = queue.peek_messages(max_messages=32)
        oldest = None
        newest = None

        if messages:
            oldest = messages[0].content
            newest = messages[-1].content

        # ✅ 지연 수준 추정
        delay_level = "normal"
        if approx >= 20:
            delay_level = "warning"
        if approx >= 50:
            delay_level = "critical"

        return success({
            "queue": queue_name,
            "approximate_message_count": approx,
            "delay_level": delay_level,
            "oldest_message": oldest,
            "newest_message": newest,
            "timestamp": datetime.utcnow().isoformat()
        })

    except Exception as e:
        return server_error(e)
    
    