import azure.functions as func
import urllib.request
import traceback

from shared.utils.api_utils import get_env
from shared.utils.time_utils import get_start_time_warmup_schedule


def main(mytimer: func.TimerRequest):
    try:
        # ✅ 환경변수
        base_url = get_env("HTTP_BASE_URL")  # 예: https://xxxx.azurewebsites.net

        # ✅ 웜업 대상 API
        endpoints = [
            "/api/isOpen",
            "/api/getSas?file=test",
            "/api/checkList?name=a&yymmdd=b"
        ]

        for ep in endpoints:
            try:
                url = base_url + ep
                print(f"[Warmup-HTTP] calling: {url}")
                urllib.request.urlopen(url, timeout=4).read()
            except Exception as e:
                print(f"[Warmup-HTTP] endpoint failed: {ep}")
                print(e)

        print("[Warmup-HTTP] done")

    except Exception as e:
        print("🔥 Warmup HTTP Timer Error")
        print(traceback.format_exc())
        