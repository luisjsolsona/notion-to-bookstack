# notion-to-bookstack

Migra exportaciones Markdown de Notion a una instancia propia de [BookStack](https://www.bookstackapp.com/).

## Características

- **Imágenes** — redimensionadas con Pillow e incrustadas como URIs base64 (no requiere servidor de imágenes externo)
- **GIFs animados** — preservados como bytes crudos, sin recodificar
- **Bloques callout** — los bloques `<aside>` de Notion se convierten en divs HTML con estilo
- **Casillas de verificación** — `- [ ]` / `- [x]` convertidas a ☐ / ☑
- **Vídeos de YouTube** — URLs sueltas y enlaces Markdown convertidos a iframes responsivos
- **Adjuntos** — PDF, DOCX, XLSX, PPTX, ZIP y más subidos automáticamente a BookStack
- **Reparación de enlaces rotos** — script auxiliar que reemplaza rutas relativas por las URLs reales de los adjuntos en BookStack
- **Compatibilidad con Notion** — nombres de carpetas truncados, IDs hexadecimales de 32 caracteres en nombres de archivo, rutas de imagen codificadas en URL
- **Modo batch** — migra múltiples exportaciones de Notion en una sola ejecución

## Requisitos

- Python 3.10+
- Una instancia de BookStack en funcionamiento con acceso a la API habilitado
- Un token de API de BookStack (Configuración → Tokens de API)

Instalar dependencias:

```bash
pip install -r requirements.txt
```

## Configuración

Edita las constantes al principio de `notion_to_bookstack.py`:

```python
BOOKSTACK_URL = "http://tu-servidor-bookstack:puerto"
TOKEN_ID      = "TU_TOKEN_ID"
TOKEN_SECRET  = "TU_TOKEN_SECRET"

# Migración de un único libro
EXPORT_ROOT = r"/ruta/a/la/exportacion/notion"
BOOK_NAME   = "Mi Libro"

# Modo batch: lista de (ruta_exportacion, nombre_libro) — tiene prioridad sobre el modo individual
BATCH: list[tuple[str, str]] = [
    (r"/ruta/exportacion1", "Libro 1"),
    (r"/ruta/exportacion2", "Libro 2"),
]
```

## Uso

### 1. Extraer el ZIP de Notion (Windows)

Las exportaciones de Notion en Windows pueden tener problemas de codificación y longitud de ruta. Usa el script auxiliar:

```bash
python extract_zip.py exportacion_notion.zip C:\destino --prefix "Mi Espacio/" --max-dir 40
```

Opciones:
- `--prefix` — prefijo de ruta a eliminar de las entradas del ZIP (por defecto: `Privado y compartido/`)
- `--max-dir` — máximo de caracteres por componente de nombre de carpeta, para evitar el límite MAX_PATH de Windows (por defecto: `40`)

### 2. Ejecutar la migración

```bash
python notion_to_bookstack.py
```

El script:
1. Se conecta a BookStack y verifica las credenciales
2. Crea un Libro (y Capítulos) siguiendo la estructura de carpetas de Notion
3. Convierte cada archivo `.md` a HTML y crea una Página
4. Sube los adjuntos encontrados en las carpetas de recursos junto a cada página

### 3. Reparar enlaces de adjuntos rotos (opcional)

Si ya existen páginas con enlaces relativos rotos, ejecuta:

```bash
python fix_attachments.py
```

Este script obtiene todos los adjuntos subidos a BookStack, busca en cada página atributos `href="..."` que apunten a rutas locales relativas y los reemplaza por las URLs reales `/attachments/{id}`.

### 4. Habilitar iframes de YouTube (opcional)

Para que los iframes de YouTube se rendericen, añade esto al `.env` o `docker-compose.yml` de BookStack:

```
ALLOWED_IFRAME_HOSTS=https://www.youtube.com https://www.youtube-nocookie.com
```

Luego reinicia el contenedor. El script de migración convierte los enlaces de YouTube automáticamente; para páginas ya migradas, vuelve a ejecutar el script o usa `fix_attachments.py`.

## Correspondencia de estructura

| Notion | BookStack |
|--------|-----------|
| Raíz de la exportación | Libro |
| Carpeta de primer nivel | Capítulo |
| Archivo `.md` | Página |
| Carpeta de recursos (imágenes, PDFs…) | Imágenes incrustadas + Adjuntos |

Las carpetas anidadas más de un nivel se aplanan automáticamente como Capítulos.

## Notas

- Las imágenes se incrustan como URIs base64 para evitar gestionar un servidor de medios externo.
  En exportaciones muy grandes esto aumenta el tamaño de las páginas; considera reducir `IMG_MAX_PX` o `IMG_QUALITY`.
- BookStack solo permite iframes de los hosts indicados en `ALLOWED_IFRAME_HOSTS`. Sin esa configuración los iframes de YouTube no se mostrarán.
- En Windows, usa rutas base cortas (p. ej. `C:\n\`) para no superar el límite de 260 caracteres de MAX_PATH.

## Licencia

MIT
