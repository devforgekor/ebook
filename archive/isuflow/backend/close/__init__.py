import azure.functions as func
import traceback

from shared.utils.api_utils import get_env
from shared.utils.settings_utils import force_close_flag


def main(mytimer: func.TimerRequest):
    try:
        # ✅ 운영 종료 강제 플래그 적용
        force_close_flag()
        print("[Close] System forced closed (ISUFLOW_OPEN = false)")

    except Exception as e:
        print("🔥 Close Timer Error")
        print(traceback.format_exc())
        