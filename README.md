# Rastreador del Calendario de Adviento de Tendry

Aplicación web en Flask que revisa periódicamente una o varias páginas de Tendry y
envía una notificación push a tu iPhone (vía [ntfy.sh](https://ntfy.sh)) en cuanto
detecta el calendario de adviento.

Incluye panel de estado, configuración editable desde el navegador, historial de
revisiones y pruebas automáticas.

> **Importante:** este proyecto no incluye una URL de Tendry inventada. Añade la
> web oficial en **Configuración** o en `DEFAULT_URLS` dentro de `.env`.

---

## Características

- Revisiones automáticas cada X minutos (15 por defecto), configurables.
- Varias URLs: portada, categoría, buscador, `sitemap.xml`, etc.
- Detección por:
  - palabras clave en el texto visible;
  - enlaces o productos cuyo nombre contiene las palabras clave;
  - cambio de disponibilidad de un producto (agotado/próximamente → comprable).
- Historial de cada revisión con fecha, URL, resultado, código HTTP y error.
- Notificación **una sola vez por hallazgo** y botón para reiniciar la alerta.
- Canales: ntfy (principal), correo SMTP, WhatsApp y Telegram (opcionales).
- Vista incrustada de la tienda de Tendry al final del panel.
- User-Agent realista, timeouts, reintentos suaves y pausas entre peticiones.
- Interfaz responsive pensada para móvil.

---

## 1. Instalación local

Requisitos: **Python 3.11 o superior** y conexión a internet.

### Windows (PowerShell)

```powershell
cd "calendario tendry"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Si PowerShell bloquea la activación, ejecuta una vez:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### macOS / Linux

```bash
cd "calendario tendry"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

---

## 2. Configurar `.env`

Abre `.env` y ajusta como mínimo:

```env
SECRET_KEY=una-cadena-larga-y-aleatoria
NTFY_TOPIC=tu-tema-secreto-de-ntfy
```

Genera la clave con:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Las URLs y las palabras clave puedes añadirlas directamente en la página de
**Configuración** una vez arrancada la app. También puedes dejarlas en `.env`:

```env
DEFAULT_URLS=Inicio | https://www.sitio-oficial.com/, Categoría | https://www.sitio-oficial.com/categoria
DEFAULT_KEYWORDS=calendario de adviento, advent calendar, adviento
CHECK_INTERVAL_MINUTES=15
```

Los valores de `.env` solo se usan para crear la configuración inicial. Después
manda lo que guardes desde la web.

Para la vista de la tienda al final del panel puedes usar `STORE_URL` o el campo
**«Tienda que se muestra al final del panel»** en Configuración. Si lo dejas
vacío, se usará la primera URL rastreada que no sea un `sitemap.xml`.

> Las credenciales SMTP, las de WhatsApp (Twilio/CallMeBot) y el token de Telegram
> se leen **solo** de `.env` y nunca se guardan en la base de datos.

---

## 3. Ejecutar la app

```bash
python run.py
```

En Windows también puedes hacer doble clic en **`iniciar.bat`**.

Abre en el navegador: **http://127.0.0.1:5000**

Al arrancar, el scheduler programa la primera revisión para unos 30 segundos
después. A partir de ahí usa el intervalo configurado.

### Ejecución en segundo plano (Windows)

Para que siga funcionando al cerrar la consola puedes crear una tarea programada
que ejecute `.venv\Scripts\pythonw.exe run.py` en la carpeta del proyecto. En
este equipo se creó la tarea **`TendryRastreador`**; puedes detenerla con
`detener.bat` y relanzarla con:

```powershell
schtasks /Run /TN "TendryRastreador"
```

### Notas sobre el modo debug

Por defecto `FLASK_DEBUG=0`, de modo que se ejecuta un único proceso estable y
el scheduler no se duplica. Si pones `FLASK_DEBUG=1` para desarrollar, Flask
activa el reloader: el scheduler detecta el proceso hijo mediante
`WERKZEUG_RUN_MAIN` y solo arranca una vez.

Si ejecutas la app con `flask run` o con un servidor WSGI, usa un solo worker
(ver despliegue).

---

## 4. Configurar ntfy en el iPhone

1. Instala **ntfy** desde la App Store.
2. Abre la app y pulsa **+** para suscribirte a un tema.
3. Escribe un tema difícil de adivinar, por ejemplo:
   `tendry-adviento-7f3a9c2e`.
4. Pega ese mismo tema en **Configuración → Tema (topic) de ntfy** o en
   `NTFY_TOPIC` del `.env`.
5. Pulsa **Probar notificación** en el panel. Debe llegar un push al iPhone.
6. Cuando el rastreador detecte el calendario, el mensaje incluirá el enlace
   directo a la página donde apareció.

Si no llega la prueba:

- Revisa que el tema esté escrito exactamente igual.
- Comprueba que la app ntfy tiene permiso de notificaciones.
- Prueba manualmente:
  `curl -d "prueba" https://ntfy.sh/tu-tema`
- El servidor `NTFY_SERVER` por defecto es `https://ntfy.sh`.

---

## 5. Correo SMTP (opcional)

Para Gmail:

1. Activa la verificación en dos pasos.
2. Crea una **contraseña de aplicación**.
3. Rellena en `.env`:

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=tu-correo@gmail.com
SMTP_PASSWORD=la-contraseña-de-aplicacion
SMTP_FROM=tu-correo@gmail.com
SMTP_USE_TLS=1
SMTP_USE_SSL=0
EMAIL_TO=tu-correo@gmail.com
```

4. Marca el canal **Correo SMTP** en Configuración.
5. Pulsa **Probar correo** al final de Configuración.

El correo se envía en texto plano y en una versión HTML con el enlace destacado.

## 6. WhatsApp (opcional)

La app soporta dos proveedores. Elige uno y rellena `.env`.

### Opción A: Twilio (oficial)

1. Crea una cuenta en [Twilio](https://www.twilio.com/) y activa el **WhatsApp Sandbox**.
2. Copia el número del sandbox y el código `join <código>`.
3. Desde tu WhatsApp, envía `join <código>` al número del sandbox.
4. Rellena `.env`:

```env
WHATSAPP_PROVIDER=twilio
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
WHATSAPP_TO=+34600111222
```

5. Guarda tu número en Configuración y marca el canal **WhatsApp**.
6. Pulsa **Probar WhatsApp**.

> El Sandbox de Twilio es para pruebas. Para enviar mensajes fuera de la ventana
> de 24 horas necesitarás una plantilla aprobada o un número de WhatsApp Business.

### Opción B: CallMeBot (gratis, no oficial)

1. Consulta el número del bot en
   [CallMeBot](https://www.callmebot.com/blog/free-api-whatsapp-messages/)
   (el número cambia y a veces está lleno).
2. Añádelo a tus contactos y envíale por WhatsApp:
   `I allow callmebot to send me messages`.
3. Recibirás un **APIKEY**.
4. Rellena `.env`:

```env
WHATSAPP_PROVIDER=callmebot
CALLMEBOT_APIKEY=tu-apikey
WHATSAPP_TO=+34600111222
```

5. Marca el canal **WhatsApp**, guarda y pulsa **Probar WhatsApp**.

> CallMeBot es un servicio no oficial para uso personal. Puede cambiar sus
> números o dejar de funcionar. Twilio es la opción oficial y más estable.

## 7. Telegram (opcional)

1. Habla con `@BotFather` y crea un bot.
2. Copia el token en `TELEGRAM_BOT_TOKEN`.
3. Envía un mensaje a tu bot y obtén tu chat ID con
   `https://api.telegram.org/bot<TOKEN>/getUpdates`.
4. Escribe el chat ID en Configuración y marca el canal **Telegram**.

---

## 8. Cómo funciona la detección

Cada ciclo revisa las URLs activas y aplica estas reglas:

1. **Palabras clave en el texto:** si aparece alguna, se marca como hallazgo.
   Si la página indica claramente “agotado” o “próximamente”, queda como
   *pendiente* y no se notifica todavía.
2. **Enlaces o productos:** si el nombre de un enlace contiene una palabra clave,
   se guarda como posible hallazgo. Si se puede visitar la ficha del producto, se
   comprueba su disponibilidad.
3. **Cambio de disponibilidad:** la primera vez que se ve un producto se guarda
   como línea base. Si antes estaba agotado/próximamente y ahora tiene stock o
   botón de compra, se notifica.

Para evitar spam:

- Cada hallazgo tiene una clave única (`url + término` o `producto`).
- Solo se notifica si `notified_at` está vacío.
- **Reiniciar alerta** borra los hallazgos y permite volver a notificar.

### Límites y buenas prácticas

- El rastreador hace **una petición por URL y ciclo**, con pausas aleatorias y un
  máximo de fichas de producto por ciclo (`MAX_PRODUCT_PAGES`).
- Respeta los términos de uso y el `robots.txt` del sitio. No reduzcas el
  intervalo a valores agresivos.
- Si el HTML cambia mucho, ajusta las palabras clave o añade URLs más estables
  (por ejemplo, la categoría o el `sitemap.xml`).
- El scraper es heurístico: los textos “agotado”, “próximamente”, “añadir al
  carrito”, etc. están en `app/scraper.py` y puedes ampliarlos.

---

## 9. Pruebas

```bash
pytest
```

Las pruebas usan HTML de ejemplo en `tests/fixtures/` y no hacen peticiones reales.
Cubren detección por texto, enlaces, sitemap, disponibilidad, notificaciones y
que no se notifique dos veces el mismo hallazgo.

---

## 10. Despliegue 24/7

La app funciona en local, pero para que rastree todo el día necesita un servidor.
En el servidor instala también el servidor WSGI:

```bash
pip install gunicorn
```

Opciones habituales:

### Render

1. Sube el proyecto a GitHub.
2. Crea un **Web Service** con:
   - Build: `pip install -r requirements.txt`
   - Start: `gunicorn --workers 1 --threads 4 --timeout 120 run:app`
3. Añade las variables de `.env` en **Environment**.
4. Very importante: usa **un solo worker** para que el scheduler no se duplique.
5. SQLite vive en el disco efímero: en el plan gratuito se pierde al reiniciar.
   Para persistencia, añade un **Persistent Disk** y apunta `DATABASE_URL` a
   `sqlite:////var/data/tendry.db`, o usa PostgreSQL.
6. Los planes gratuitos se duermen por inactividad. Para un rastreo real 24/7 usa
   un plan de pago o un servicio de *ping* externo.

### Railway

1. Crea un proyecto desde el repositorio.
2. Añade las variables de entorno.
3. Comando de arranque:
   `gunicorn --workers 1 --threads 4 --timeout 120 run:app`
4. Añade un volumen persistente para la base de datos si quieres conservar el
   historial.

### PythonAnywhere

1. Sube el código y crea un virtualenv.
2. Instala las dependencias.
3. Configura una web app WSGI apuntando a `run:app`.
4. El scheduler de APScheduler dentro del proceso web puede detenerse si el
   worker se recicla. Para algo crítico, usa una **Always-on task** que ejecute
   un script de revisión, o un cron externo que llame a la app.

> En cualquier despliegue: un solo proceso con el scheduler activo. Si escalas a
> varios workers, desactiva `SCHEDULER_ENABLED` y ejecuta el job aparte.

---

## 11. Estructura del proyecto

```
app/
  __init__.py      # create_app, filtros, CSRF, arranque del scheduler
  config.py        # configuración desde .env
  extensions.py    # SQLAlchemy y APScheduler
  models.py        # modelos y datos iniciales
  routes.py        # panel, configuración, historial y acciones
  scraper.py       # descarga, detección y revisiones
  notifier.py      # ntfy, email, WhatsApp y Telegram
  scheduler.py     # job periódico sin duplicados
  utils.py         # texto, URLs, keywords y CSRF
  templates/       # Jinja2 responsive
  static/css/      # estilos mobile-first
tests/             # pytest + HTML de ejemplo
run.py             # entrada local
requirements.txt
.env.example
pytest.ini
```

---

## 12. Problemas frecuentes

| Problema | Solución |
| --- | --- |
| No llega la notificación | Revisa el tema de ntfy y pulsa “Probar notificación”. |
| “Token CSRF inválido” | Recarga la página; la sesión caducó. |
| El scheduler no revisa | Comprueba que el rastreo no esté pausado y `SCHEDULER_ENABLED=1`. |
| La web devuelve error HTTP | Puede haber bloqueo, timeout o cambio de HTML. Revisa el historial. |
| El calendario aparece pero no notifica | Puede estar marcado como “próximamente”; espera al cambio de stock. |
| Quiero que vuelva a avisar | Pulsa “Reiniciar alerta”. |
| SQLite se pierde al desplegar | Usa un disco persistente o PostgreSQL. |
