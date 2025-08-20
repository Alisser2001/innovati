import asyncio
from datetime import datetime

from app.config import settings
from app.email.client import GraphClient
from app.nlp.parser import extract_intent_sql_like
import re

def _html_to_text(html: str | None) -> str:
    if not html:
        return ""
    return re.sub(r"<[^>]+>", " ", html).replace("&nbsp;", " ").strip()

async def run_poller():
    if not all([settings.GRAPH_TENANT_ID, settings.GRAPH_CLIENT_ID, settings.GRAPH_CLIENT_SECRET, settings.GRAPH_USER_UPN]):
        print("[poller] Falta configuración GRAPH_* en .env. Poller deshabilitado.")
        return
    client = GraphClient(
        tenant_id=settings.GRAPH_TENANT_ID,
        client_id=settings.GRAPH_CLIENT_ID,
        client_secret=settings.GRAPH_CLIENT_SECRET,
        user_upn=settings.GRAPH_USER_UPN,
    )
    try:
        interval = max(5, int(settings.GRAPH_POLL_INTERVAL_SECONDS))
        print(f"[poller] Iniciado. Intervalo: {interval}s | Buzón: {settings.GRAPH_USER_UPN}")
        while True:
            try:
                unread = await client.list_unread_messages(top=5)
                if unread:
                    print(f"[poller] Encontrados {len(unread)} mensaje(s) no leídos.")
                for msg in unread:
                    msg_id = msg["id"]
                    full = await client.get_message(msg_id)
                    subject = full.get("subject") or "(sin asunto)"
                    from_email = (full.get("from") or {}).get("emailAddress", {}).get("address") or ""
                    body_html = (full.get("body") or {}).get("content") or ""
                    body_text = _html_to_text(body_html) or (full.get("bodyPreview") or "")
                    try:
                        intent_data, sql_like = await extract_intent_sql_like(subject, body_text)
                    except Exception as e:
                        intent_data = {"intent": "unknown", "params": {}, "confidence": 0.0, "reason": f"llm-error: {e}"}
                        sql_like = "-- no-sql (error LLM)"
                    reply = (
                        "¡Hola! 👋\n\n"
                        "Analicé tu correo y esto es lo que entiendo que necesitas:\n\n"
                        f"- intent: {intent_data.get('intent')}\n"
                        f"- params: {intent_data.get('params')}\n"
                        f"- confidence: {intent_data.get('confidence')}\n"
                        f"- reason: {intent_data.get('reason')}\n\n"
                        "Representación tipo SQL:\n"
                        f"{sql_like}\n\n"
                        f"(Procesado: {datetime.utcnow().isoformat()}Z)"
                    )
                    if from_email:
                        await client.send_mail(to_email=from_email, subject=f"Re: {subject}", body_text=reply)
                    await client.mark_as_read(msg_id, True)
                await asyncio.sleep(interval)
            except Exception as ex:
                print(f"[poller] Error en ciclo: {ex}")
                await asyncio.sleep(interval * 2)
    finally:
        await client.aclose()
