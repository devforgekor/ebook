from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from apps.notifier.core.config import settings

security = HTTPBearer()

async def verify_api_key(auth: HTTPAuthorizationCredentials = Security(security)):
    if auth.credentials != settings.NOTIFIER_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid or missing API Key")
    return auth.credentials
