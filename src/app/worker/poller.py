import asyncio
from datetime import datetime
import re
from app.config import settings
from app.email.client import GraphClient
from app.nlp.parser import extract_intent_sql_like
from app.db import SessionLocal
from app.models import EmailLog
from app.actions import list_books, register_book, register_copy, reserve, renew, cancel

def _html_to_text(html: str | None) -> str:
    if not html:
        return ""
    return re.sub(r"<[^>]+>", " ", html).replace("&nbsp;", " ").strip()

def _friendly_reply(intent: str, params: dict, result: dict, processed_at_iso: str) -> str:
    success = result.get("ok", False)
    detail = result.get("data") or {}
    def who():
        email = params.get("email") or detail.get("user_email")
        name = params.get("name")
        if name and email:
            return f"{name} ({email})"
        return email or name or "usuario"
    def book_label():
        return (
            params.get("book_title")
            or detail.get("title")
            or params.get("title")
            or "el libro solicitado"
        )
    def copy_label():
        return params.get("barcode") or detail.get("barcode") or "la copia indicada"
    if intent == "reserve":
        msg = "La reserva del libro solicitado se realizó exitosamente." if success \
              else "No pudimos realizar la reserva porque no hay copias disponibles o el libro no existe."
    elif intent == "renew":
        msg = "La reservación fue renovada exitosamente." if success \
              else "No pudimos renovar la reservación. Verifica el código de barras y el correo."
    elif intent == "cancel":
        msg = "La reservación fue cancelada exitosamente." if success \
              else "No encontramos una reservación activa para cancelar con esos datos."
    elif intent == "list_books":
        msg = "Te envío el listado actualizado de libros." if success \
              else "No fue posible obtener el listado en este momento."
    elif intent == "register_book":
        msg = f"Se registró el libro “{book_label()}” correctamente." if success \
              else "No pudimos registrar el libro. Revisa los datos enviados."
    elif intent == "register_copy":
        msg = f"Se registró la copia ({copy_label()}) correctamente." if success \
              else "No pudimos registrar la copia. Revisa el código de barras y el libro."
    else:
        msg = "No entendí tu solicitud. ¿Podrías darme un poco más de contexto?"
    lines = ["¡Hola! 👋", ""]
    lines.append(msg)
    if intent == "reserve" and success:
        if detail.get("due_date"):
            lines.append(f"Fecha de vencimiento de la reserva: {detail['due_date']}.")
    if intent == "list_books" and success:
        items = (result.get("data") or {}).get("items") or []
        if items:
            total = sum(i.get("copies_total", 0) for i in items)
            disp = sum(i.get("copies_available", 0) for i in items)
            lines.append(f"Libros en catálogo: {len(items)} · Copias totales: {total} · Disponibles ahora: {disp}.")
    lines.append("")
    lines.append(f"(Procesado: {processed_at_iso}Z)")
    return "\n".join(lines)

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
                    print(f"[poller] {len(unread)} no leídos.")
                for msg in unread:
                    msg_id = msg["id"]
                    full = await client.get_message(msg_id)
                    subject = full.get("subject") or "(sin asunto)"
                    from_obj = (full.get("from") or {}).get("emailAddress") or {}
                    from_email = from_obj.get("address") or ""
                    from_name = from_obj.get("name") or ""
                    body_html = (full.get("body") or {}).get("content") or ""
                    body_text = _html_to_text(body_html) or (full.get("bodyPreview") or "")
                    try:
                        intent_data, sql_like = await extract_intent_sql_like(subject, body_text)
                    except Exception as e:
                        intent_data = {"intent": "unknown", "params": {}, "confidence": 0.0, "reason": f"llm-error: {e}"}
                        sql_like = "-- no-sql (error LLM)"

                    intent = (intent_data.get("intent") or "unknown").strip()
                    params = intent_data.get("params") or {}
                    async with SessionLocal() as session:
                        result = {"ok": False, "message": "No se pudo procesar la solicitud.", "code": "UNHANDLED_INTENT"}
                        try:
                            if intent == "list_books":
                                result = await list_books(session)
                            elif intent == "register_book":
                                result = await register_book(session, title=params.get("title"), author=params.get("author"))
                            elif intent == "register_copy":
                                result = await register_copy(session, book_id=params.get("book_id"), barcode=params.get("barcode"), location=params.get("location"))
                            elif intent == "reserve":
                                result = await reserve(session,
                                    book_id=params.get("book_id"),
                                    book_title=params.get("book_title"),
                                    name=params.get("name") or from_name,
                                    email=params.get("email") or from_email
                                )
                            elif intent == "renew":
                                result = await renew(session, barcode=params.get("barcode"), email=params.get("email") or from_email)
                            elif intent == "cancel":
                                result = await cancel(session, barcode=params.get("barcode"), email=params.get("email") or from_email)
                            else:
                                result = {"ok": False, "message": f"No entendí la solicitud. ({intent_data.get('reason','sin razón')})", "code": "UNKNOWN_INTENT"}
                        except Exception as action_ex:
                            result = {"ok": False, "message": f"Error interno al ejecutar la operación: {action_ex}", "code": "ACTION_ERROR"}
                        processed_at_iso = datetime.utcnow().isoformat()
                        reply = _friendly_reply(intent, params, result, processed_at_iso)
                        if from_email:
                            await client.send_mail(to_email=from_email, subject=f"Re: {subject}", body_text=reply)
                        await client.mark_as_read(msg_id, True)
                        log = EmailLog(
                            message_id=msg_id,
                            from_email=from_email or "",
                            subject=subject,
                            processed=True,
                            processed_at=datetime.utcnow(),
                        )
                        session.add(log)
                        await session.commit()
                await asyncio.sleep(interval)
            except Exception as ex:
                print(f"[poller] Error en ciclo: {ex}")
                await asyncio.sleep(interval * 2)
    finally:
        await client.aclose()
