import azure.functions as func
import traceback
from azure.storage.queue import QueueClient

from shared.utils.api_utils import get_env


def main(mytimer: func.TimerRequest):
    try:
        conn = get_env("AzureWebJobsStorage")

        # ✅ dummy warmup 메시지 생성
        queue = QueueClient.from_connection_string(
            conn, "processpdf"
        )

        queue.send_message('{"warmup": true}')

        print("[Warmup-Queue] dummy job pushed")

    except Exception as e:
        print("🔥 Warmup Queue Timer Error")
        print(traceback.format_exc())
        