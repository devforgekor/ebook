import json
from azure.storage.blob import BlobClient
import os

def load_settings():
    """
    Settings JSON을 Azure Blob Storage에서 불러오는 함수.
    local.settings.json의 SETTINGS_BLOB_PATH 값을 기준으로 가져온다.
    """

    conn_str = os.environ.get("AzureWebJobsStorage")
    blob_path = os.environ.get("SETTINGS_BLOB_PATH", "config/settings.json")

    blob = BlobClient.from_connection_string(
        conn_str,
        container_name=blob_path.split("/")[0],
        blob_name="/".join(blob_path.split("/")[1:])
    )

    data = blob.download_blob().readall()
    return json.loads(data)

