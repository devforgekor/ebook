from fastapi import APIRouter, HTTPException, Depends
from apps.notifier.providers import get_provider
from apps.notifier.core.security import verify_api_key
from pydantic import BaseModel

router = APIRouter()

class NotifyRequest(BaseModel):
    text: str
    channel: str = "telegram"

@router.post("/v1/notify")
async def send_notification(
    request: NotifyRequest,
    _=Depends(verify_api_key)
):
    provider = get_provider(request.channel)
    if not provider:
        raise HTTPException(400, f"Unsupported channel: {request.channel}")
    try:
        result = await provider.send(request.text)
        if result:
            return {"status": "ok", "channel": request.channel}
        else:
            return {"status": "fail", "channel": request.channel, "message": "Provider send failed"}
    except Exception as e:
        return {"status": "error", "channel": request.channel, "message": str(e)}
