from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter(prefix="/oauth", tags=["oauth"])

LOGIN_PAGE = """
<!DOCTYPE html>
<html lang="ru">
<head><meta charset="utf-8"><title>OAuth Login</title></head>
<body>
  <h1>Smart Classroom — вход</h1>
  <form method="post" action="/oauth/authorize">
    <input type="hidden" name="client_id" value="{client_id}">
    <input type="hidden" name="redirect_uri" value="{redirect_uri}">
    <input type="hidden" name="state" value="{state}">
    <input type="hidden" name="scope" value="{scope}">
    <label>Email <input type="email" name="email"></label>
    <label>Пароль <input type="password" name="password"></label>
    <button type="submit">Войти</button>
  </form>
</body>
</html>
"""


@router.get("/authorize", response_class=HTMLResponse)
async def authorize(
    client_id: str = "",
    redirect_uri: str = "",
    state: str = "",
    response_type: str = "code",
    scope: str = "classroom:control",
) -> str:
    return LOGIN_PAGE.format(client_id=client_id, redirect_uri=redirect_uri, state=state, scope=scope)


@router.post("/authorize")
async def authorize_submit(
    email: str = Form(default=""),
    password: str = Form(default=""),
    client_id: str = Form(default=""),
    redirect_uri: str = Form(default=""),
    state: str = Form(default=""),
    scope: str = Form(default="classroom:control"),
) -> RedirectResponse:
    if not redirect_uri:
        raise HTTPException(status_code=400, detail="redirect_uri is required")
    code = "stub_auth_code"
    separator = "&" if "?" in redirect_uri else "?"
    return RedirectResponse(
        url=f"{redirect_uri}{separator}code={code}&state={state}&client_id={client_id}&scope={scope}",
        status_code=302,
    )


@router.post("/token")
async def token(grant_type: str = "authorization_code") -> dict[str, object]:
    return {
        "access_token": "stub_access_token",
        "token_type": "Bearer",
        "expires_in": 3600,
        "refresh_token": "stub_refresh_token",
        "scope": "classroom:control",
    }


@router.post("/revoke")
async def revoke() -> dict[str, bool]:
    return {"revoked": True}
