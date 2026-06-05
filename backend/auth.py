from fastapi import Request, HTTPException, status
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from backend.config_loader import SESSION_SECRET

# Sessions expire after 30 days (timed serializer) so a leaked cookie isn't valid forever.
SESSION_MAX_AGE_SECONDS = 30 * 24 * 60 * 60

serializer = URLSafeTimedSerializer(SESSION_SECRET)

def create_session_token(authenticated: bool = True) -> str:
    return serializer.dumps({"auth": authenticated})

def verify_session_token(token: str) -> bool:
    try:
        data = serializer.loads(token, max_age=SESSION_MAX_AGE_SECONDS)
        return data.get("auth", False)
    except (SignatureExpired, BadSignature):
        return False

async def get_current_user(request: Request):
    token = request.cookies.get("session")
    if not token or not verify_session_token(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    return True
