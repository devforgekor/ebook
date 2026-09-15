import azure.functions as func
import traceback

from shared.utils.api_utils import get_env
from shared.utils.archive_utils import (
    run_generation_archive,
    should_archive_today
)


def main(mytimer: func.TimerRequest):
    try:
        if not should_archive_today():
            print("[Archive] Not archive date. Skipped.")
            return

        conn = get_env("AzureWebJobsStorage")

        print("[Archive] Starting archive process...")
        result = run_generation_archive(conn)

        print("[Archive] ✅ Archive completed")
        print(result)

    except Exception as e:
        print("🔥 Archive Timer Error")
        print(traceback.format_exc())
        