import azure.functions as func
import traceback

from shared.utils.api_utils import get_env
from shared.utils.schedule_utils import rebuild_off_schedule_from_settings
from shared.utils.shadowindex_utils import sync_tags_and_shadowindex


def main(mytimer: func.TimerRequest):
    try:
        conn = get_env("AzureWebJobsStorage")

        # ✅ OFF_SCHEDULE 재계산
        rebuild_off_schedule_from_settings(conn)

        # ✅ ShadowIndex ↔ Blob Tags diff 검사
        sync_tags_and_shadowindex(conn)

        print("[Midnight-Fix] nightly check completed")

    except Exception as e:
        print("🔥 Midnight Fix Timer Error")
        print(traceback.format_exc())
        