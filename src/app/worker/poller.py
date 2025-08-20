import asyncio
from datetime import datetime
import re
from app.config import settings
from app.email.client import GraphClient
from app.nlp.parser import extract_intent_sql_like
from app.db import SessionLocal
from app.models import EmailLog
from app.actions import list_books, register_book, register_copy, reserve, renew, cancel, delete_book

def _html_to_text(html: str | None) -> str:
    if not html:
        return ""
    return re.sub(r"<[^>]+>", " ", html).replace("&nbsp;", " ").strip()

def _friendly_reply(intent: str, params: dict, result: dict, processed_at_iso: str) -> str:
    success = result.get("ok", False)
    data = result.get("data") or {}
    code = result.get("code") or ""
    def _val(k, alt=None): return data.get(k) or params.get(k) or alt
    def _line_items(lines: list[str]) -> list[str]:
        return [f"- {ln}" for ln in lines if ln]
    def _header(txt: str) -> str:
        return txt.strip()
    lines: list[str] = ["¡Hola! 👋", ""]
    if intent == "reserve":
        if success:
            lines.append(_header("✅ Reserva realizada con éxito."))
            items = _line_items([
                f"Libro: {_val('title', 'desconocido')} (ID: {_val('book_id','-')})",
                f"Copia (barcode): {_val('barcode','-')}",
                f"Ubicación: {_val('location','-')}",
                f"Usuario: {_val('user_email','-')}",
                f"Vencimiento: {_val('due_date','-')}",
                f"Renovaciones: {_val('renewed_cnt', 0)}",
                f"Id de reservación: {_val('reservation_id','-')}",
            ])
            lines += items
        else:
            msg = {
                "BOOK_NOT_FOUND": "No encontré el libro por id/título.",
                "NO_AVAILABLE_COPIES": "No hay copias disponibles para ese libro.",
                "MISSING_EMAIL": "Falta el correo del solicitante."
            }.get(code, result.get("message") or "No pudimos realizar la reserva.")
            lines.append(f"❌ {msg}")
    elif intent == "renew":
        if success:
            lines.append(_header("🔁 Renovación exitosa."))
            items = _line_items([
                f"Copia (barcode): {_val('barcode','-')}",
                f"Libro: {_val('title','-')} (ID: {_val('book_id','-')})",
                f"Usuario: {_val('user_email','-')}",
                f"Nuevo vencimiento: {_val('due_date','-')}",
                f"Total de renovaciones: {_val('renewed_cnt','-')}",
                f"Id de reservación: {_val('reservation_id','-')}",
            ])
            lines += items
        else:
            msg = {
                "MISSING_FIELDS": "Debes enviar barcode y email.",
                "USER_NOT_FOUND": "No encontré al usuario.",
                "COPY_NOT_FOUND": "No encontré la copia indicada.",
                "ACTIVE_RESERVATION_NOT_FOUND": "No hay una reservación activa para esos datos.",
                "RESERVATION_EXPIRED": "La reservación está vencida; no se puede renovar."
            }.get(code, result.get("message") or "No pudimos renovar la reservación.")
            lines.append(f"❌ {msg}")
    elif intent == "cancel":
        if success:
            lines.append(_header("🗑️ Reservación cancelada."))
            items = _line_items([
                f"Libro: {_val('title','-')} (ID: {_val('book_id','-')})",
                f"Copia (barcode): {_val('barcode','-')}",
                f"Usuario: {_val('user_email','-')}",
                f"Cancelado en: {_val('canceled_at','-')}",
                f"Id de reservación: {_val('reservation_id','-')}",
            ])
            lines += items
        else:
            msg = {
                "MISSING_FIELDS": "Debes enviar barcode y email.",
                "USER_NOT_FOUND": "No encontré al usuario.",
                "COPY_NOT_FOUND": "No encontré la copia indicada.",
                "ACTIVE_RESERVATION_NOT_FOUND": "No hay una reservación activa para esos datos."
            }.get(code, result.get("message") or "No pudimos cancelar la reservación.")
            lines.append(f"❌ {msg}")
    elif intent == "register_book":
        if success:
            lines.append(_header("📚 Libro registrado correctamente."))
            items = _line_items([
                f"Título: {_val('title','-')}",
                f"Autor: {_val('author','-')}",
                f"ID: {_val('book_id','-')}",
                f"Creado en: {_val('created_at','-')}",
            ])
            lines += items
        else:
            msg = {
                "MISSING_TITLE": "Falta el título del libro."
            }.get(code, result.get("message") or "No pudimos registrar el libro.")
            lines.append(f"❌ {msg}")
    elif intent == "register_copy":
        if success:
            lines.append(_header("🧾 Copia registrada correctamente."))
            items = _line_items([
                f"Libro: {_val('title','-')} (ID: {_val('book_id','-')})",
                f"Copia (barcode): {_val('barcode','-')}",
                f"Ubicación: {_val('location','-')}",
                f"ID de copia: {_val('copy_id','-')}",
            ])
            lines += items
        else:
            msg = {
                "MISSING_FIELDS": "Faltan book_id, barcode o location.",
                "BOOK_NOT_FOUND": "El libro indicado no existe.",
                "BARCODE_EXISTS": "El código de barras ya existe."
            }.get(code, result.get("message") or "No pudimos registrar la copia.")
            lines.append(f"❌ {msg}")
    elif intent == "list_books":
        if success:
            items = (data.get("items") or [])
            total = sum(i.get("copies_total", 0) for i in items)
            disp = sum(i.get("copies_available", 0) for i in items)
            lines.append(_header("📖 Listado de libros (primeros 10):"))
            for idx, it in enumerate(items[:10], start=1):
                title = it.get("title") or "-"
                author = it.get("author") or "-"
                bid = it.get("book_id") or "-"
                ct = it.get("copies_total", 0)
                ca = it.get("copies_available", 0)
                lines.append(f"{idx}) {title} — {author} | Copias: {ca}/{ct} (ID: {bid})")
            lines.append("")
            lines.append(f"Resumen: Libros: {len(items)} · Copias totales: {total} · Disponibles: {disp}.")
        else:
            lines.append("❌ No fue posible obtener el listado en este momento.")
    elif intent == "delete_book":
        if success:
            lines.append(_header("🧹 Libro eliminado."))
            items = _line_items([
                f"Título: {_val('title','-')}",
                f"ID: {_val('book_id','-')}",
                f"Copias eliminadas: {_val('removed_copies',0)}",
                f"Reservaciones eliminadas: {_val('removed_reservations',0)}",
            ])
            lines += items
        else:
            msg = {
                "MISSING_ID_OR_TITLE": "Debes indicar el id o el título del libro.",
                "BOOK_NOT_FOUND": "No encontré el libro solicitado."
            }.get(code, result.get("message") or "No pudimos eliminar el libro.")
            lines.append(f"❌ {msg}")
    else:
        lines.append("🤖 No entendí tu solicitud. ¿Podrías darme un poco más de contexto?")
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
                            elif intent == "delete_book":
                                result = await delete_book(
                                    session,
                                    book_id=params.get("book_id"),
                                    book_title=params.get("book_title"),
                                )
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
