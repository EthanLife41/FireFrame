from fastapi import Request, HTTPException, status
from itsdangerous import URLSafeSerializer, BadSignature
from backend.config_loader import SESSION_SECRET, DASHBOARD_PASSWORD

serializer = URLSafeSerializer(SESSION_SECRET)

def create_session_token(authenticated: bool = True) -> str:
    return serializer.dumps({"auth": authenticated})

def verify_session_token(token: str) -> bool:
    try:
        data = serializer.loads(token)
        return data.get("auth", False)
    except BadSignature:
        return False

async def get_current_user(request: Request):
    token = request.cookies.get("session")
    if not token or not verify_session_token(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    return True
