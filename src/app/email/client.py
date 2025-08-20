import time
from typing import Any, Dict, List, Optional
import httpx
import re

class GraphClient:
    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        user_upn: str,
        base_url: str = "https://graph.microsoft.com/v1.0",
        token_url_tpl: str = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
    ):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.user_upn = user_upn
        self.base_url = base_url
        self.token_url = token_url_tpl.format(tenant=tenant_id)

        self._access_token: Optional[str] = None
        self._exp_epoch: float = 0.0
        self._http = httpx.AsyncClient(timeout=20)

    async def aclose(self):
        await self._http.aclose()

    async def _get_token(self) -> str:
        now = time.time()
        if self._access_token and now < (self._exp_epoch - 60):
            return self._access_token

        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        }
        resp = await self._http.post(self.token_url, data=data)
        resp.raise_for_status()
        payload = resp.json()
        self._access_token = payload["access_token"]
        self._exp_epoch = now + int(payload.get("expires_in", 3600))
        return self._access_token

    async def _auth_headers(self) -> Dict[str, str]:
        token = await self._get_token()
        return {"Authorization": f"Bearer {token}"}

    async def list_unread_messages(self, top: int = 5) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/users/{self.user_upn}/mailFolders/inbox/messages"
        params = {
            "$filter": "isRead eq false",
            "$orderby": "receivedDateTime desc",
            "$top": str(top),
            "$select": "id,subject,from,receivedDateTime,bodyPreview",
        }
        resp = await self._http.get(url, headers=await self._auth_headers(), params=params)
        resp.raise_for_status()
        return resp.json().get("value", [])

    async def send_mail(self, to_email: str, subject: str, body_text: str) -> None:
        url = f"{self.base_url}/users/{self.user_upn}/sendMail"
        payload = {
            "message": {
                "subject": subject,
                "body": {"contentType": "Text", "content": body_text},
                "toRecipients": [{"emailAddress": {"address": to_email}}],
            }
        }
        resp = await self._http.post(url, headers=await self._auth_headers(), json=payload)
        resp.raise_for_status()

    async def mark_as_read(self, message_id: str, is_read: bool = True) -> None:
        url = f"{self.base_url}/users/{self.user_upn}/messages/{message_id}"
        payload = {"isRead": is_read}
        resp = await self._http.patch(url, headers=await self._auth_headers(), json=payload)
        resp.raise_for_status()

    async def get_message(self, message_id: str) -> dict:
        url = f"{self.base_url}/users/{self.user_upn}/messages/{message_id}"
        params = {"$select": "id,subject,from,receivedDateTime,body,bodyPreview"}
        resp = await self._http.get(url, headers=await self._auth_headers(), params=params)
        resp.raise_for_status()
        return resp.json()

    def html_to_text(html: str) -> str:
        if not html: return ""
        return re.sub(r"<[^>]+>", " ", html).replace("&nbsp;", " ").strip()
