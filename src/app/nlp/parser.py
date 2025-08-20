from typing import Literal, Tuple, Dict, Any
from pydantic import BaseModel, Field
from langchain.prompts import PromptTemplate, ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain.schema import SystemMessage, HumanMessage
from app.nlp.client import GeminiClient

DOMAIN_CONTEXT = """
                Tienes un sistema de biblioteca con las siguientes entidades y campos:

                - book(id, title, author, created_at)
                - book_copie(id, book_id, barcode, status, location)
                - email_user(id, email, name)
                - reservations(id, email_user_id, book_id, copy_id, status, start_date, due_date, canceled_at, renewed_cnt)

                Estados:
                - CopyStatus: AVAILABLE, RESERVED, LOANED, LOST, DAMAGED
                - ReservationStatus: ACTIVE, CANCELED, EXPIRED

                Operaciones típicas (intent):
                - reserve(book_id, name, email)
                - renew(barcode, email)
                - cancel_by_barcode_email(barcode, email)
                - list_books()
                - register_book(title, author)
                - register_copy(book_id, barcode, location)
                """

INSTRUCTIONS = """
                Eres un parser de intención para una API de biblioteca.
                Lee el asunto y el cuerpo del correo. Deduce la intención del usuario (intent) y los parámetros (params).
                Debes devolver un JSON **estricto** que cumpla con el siguiente esquema:

                - intent: uno de {reserve | renew | cancel | list_books | register_book | register_copy | unknown}
                - params: objeto con campos adecuados para el intent
                - reserve: { "book_title"?:string, "book_id"?:string, "name":string, "email":string }
                - renew:   { "barcode":string, "email":string }
                - cancel:  { "barcode":string, "email":string }
                - list_books: {}
                - register_book:  { "title":string, "author"?:string }
                - register_copy:  { "book_id":string, "barcode":string, "location":string }
                - confidence: número entre 0 y 1
                - reason: texto corto justificando por qué crees esa intención
                - sql_like: una sola cadena con una *pseudoconsulta* SQL que describe la acción/consulta que harías

                Si faltan datos críticos, usa intent=unknown o completa params con vacíos y baja confidence.
                Responde **solo** el JSON final, sin texto extra, sin markdown, sin backticks.
                """

class IntentPayload(BaseModel):
    intent: Literal["reserve", "renew", "cancel", "list_books", "register_book", "register_copy", "unknown"] = Field(..., description="Intent detectado")
    params: Dict[str, Any] = Field(default_factory=dict, description="Parámetros necesarios para la operación")
    confidence: float = Field(ge=0, le=1, default=0.0, description="Confianza en la clasificación")
    reason: str = Field(default="", description="Breve justificación de la clasificación")
    sql_like: str = Field(default="-- no-sql", description="Pseudoconsulta SQL representando la operación")

# Parser que validará que el LLM devuelva el JSON correcto:
json_parser = JsonOutputParser(pydantic_object=IntentPayload)

# Prompt (estilo chat) con instrucciones + variables
SYSTEM_TMPL = ChatPromptTemplate.from_messages([
    SystemMessage(content=DOMAIN_CONTEXT),
    SystemMessage(content=INSTRUCTIONS + "\n\n" + json_parser.get_format_instructions()),
])

HUMAN_TMPL = PromptTemplate(
    template=(
        "# CORREO\n"
        "Asunto: {subject}\n\n"
        "Cuerpo:\n"
        "{body}\n"
    ),
    input_variables=["subject", "body"],
)

async def extract_intent_sql_like(subject: str, body_text: str) -> Tuple[dict, str]:
    subj = (subject or "").strip() or "(sin asunto)"
    body = (body_text or "").strip() or "(sin cuerpo)"
    client = GeminiClient()

    system_msgs = SYSTEM_TMPL.format_messages()
    human_msg = HumanMessage(content=HUMAN_TMPL.format(subject=subj, body=body))
    messages = [*system_msgs, human_msg]

    resp = await client.ainvoke(messages)

    raw_text = (resp.content or "").strip()

    try:
        payload: IntentPayload = json_parser.parse(raw_text)
    except Exception as e:
        logger.debug("[parser] Error parseando JSON del LLM: %s ; raw: %s", e, raw_text[:600])
        return {"intent": "unknown", "params": {}, "confidence": 0.0, "reason": f"parse-error: {e}"}, "-- no-sql"

    if isinstance(payload, BaseModel):
        data = payload.model_dump()
    elif isinstance(payload, dict):
        data = payload
    else:
        try:
            data = IntentPayload(**payload).model_dump()
        except Exception:
            return {"intent": "unknown", "params": {}, "confidence": 0.0, "reason": "unexpected-payload-type"}, "-- no-sql"
    sql_like = data.get("sql_like") or "-- no-sql"
    return data, sql_like