# Prueba Técnica Innovati - Biblioteca por Correo

## Arquitectura (alto nivel)

- **FastAPI** arranca un **poller** que lee periódicamente el buzón vía **Microsoft Graph**.
- **LangChain + Gemini** interpreta el correo y genera **SQL seguro** para **SQLAlchemy**.
- Se ejecuta la transacción (DB **PostgreSQL en Azure** o **SQLite** en local) y se envía una respuesta en **lenguaje natural** al remitente.
- **Despliegue** en **Azure Container Apps (ACA)** con **CI/CD** vía **GitHub Actions** para la generación y publicación continua de contenedores.

## Variables de Entorno

Define estas variables (puedes exportarlas en tu entorno o usar un archivo `.env`).

- `DATABASE_URL` — Para desarrollo: `sqlite+aiosqlite:///./library.db`. En producción: URL de Azure Database for PostgreSQL.
- `GRAPH_TENANT_ID`
- `GRAPH_CLIENT_ID`
- `GRAPH_CLIENT_SECRET`
- `GRAPH_USER_UPN`
- `GRAPH_POLL_INTERVAL_SECONDS`
- `ENABLE_EMAIL_POLLER` (`true`/`false`)
- `GEMINI_API_KEY`
- `GEMINI_MODEL`
- `GEMINI_TIMEOUT`

## Ejecución local

### Con venv

```bash
python -m venv .venv
source .venv/bin/activate

pip install -e .[llm,test]

# Correr tests
pytest -q

# Levantar API (asumiendo paquete en src/ y app.main:app)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --app-dir src
```

### Con Docker

```bash
# Build & up
docker compose up -d --build

# Correr tests dentro del contenedor de la API
docker compose exec api pytest -q
```

## Documentación API

- **Swagger UI**: `/docs`
- **OpenAPI JSON**: `/openapi.json`

> Si corres en local con el puerto por defecto, prueba: `http://localhost:8000/docs`.

## Despliegue en Azure

1. Crear una **DB** en *Azure Database for PostgreSQL*.
2. Crear un **Azure Container Registry (ACR)** básico.
3. Crear una **Azure Container App (ACA)**.
4. Conectar la **ACA** con la **ACR** en la pestaña **Contenedores**.
5. En **Implementación**, conectar la ACA con tu **GitHub** para habilitar una **GitHub Action** de despliegue continuo desde la rama `main`, apuntando a `./Dockerfile`.
6. Añadir las **variables de entorno de producción** en **Contenedores**, incluyendo la `DATABASE_URL` de la DB creada en Azure.

## Formatos de Correo Soportados

Escribe en lenguaje natural: el parser extrae intención y datos. Ejemplos:

### Registrar libro

**Asunto:** `Registrar libro: <NOMBRE_DEL_LIBRO>`  
**Cuerpo:**
```
Agrega un libro con título <NOMBRE_DEL_LIBRO> y autor <NOMBRE_DEL_AUTOR>.
```

### Registrar copia

**Asunto:** `Nueva copia para un libro`  
**Cuerpo:**
```
Registra una copia para el libro con id <BOOK_ID>.
Código de barras: <BARCODE_UNICO>
Ubicación: <UBICACION>
```

### Listar libros

**Asunto:** `¿Qué libros tienen disponibles?`  
**Cuerpo:**
```
Quiero el listado de libros con la cantidad de copias disponibles.
```

### Eliminar libro

**Asunto:** `Eliminar libro`  
**Cuerpo:**
```
Borra el libro <NOMBRE_DEL_LIBRO>.
```

### Reservar libro

**Asunto:** `Reservar libro`  
**Cuerpo:**
```
Quiero reservar el libro <NOMBRE_DEL_LIBRO>.
Mi nombre es <TU_NOMBRE> y mi correo es <TU_CORREO>.
```

### Renovar reserva

**Asunto:** `Renovar mi reserva`  
**Cuerpo:**
```
Quiero renovar la reservación de la copia con código de barras <BARCODE>.
Mi correo es <TU_CORREO>.
```

### Cancelar reserva

**Asunto:** `Cancelar mi reservación`  
**Cuerpo:**
```
Cancela la reservación de la copia con código de barras <BARCODE>.
Mi correo es <TU_CORREO>.
```
