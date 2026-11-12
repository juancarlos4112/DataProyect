# Órdenes de Servicio — Mantención de Rack

App web (móvil primero) para que los técnicos registren mantenciones de rack con
fotos, checklist y firma, y envíen automáticamente la orden en PDF al cliente.

## Funcionalidades

- **Mantenedor de clientes**: razón social, RUT, contacto, correo, teléfono, dirección.
- **Mantenedor de proyectos/sitios**: cliente, dirección, racks y **correos destinatarios** (To y CC).
- **Usuarios**: administradores y técnicos (cada técnico ve solo sus órdenes).
- **Orden de servicio**: datos, checklist de 8 puntos con observaciones, trabajo realizado,
  materiales, observaciones, fotos antes/después y firma en pantalla.
- **Fotos**: se comprimen en el teléfono y en el servidor (máx. 1600 px, JPEG 82 %).
- **PDF**: documento formal con logo, datos, checklist, fotos y firma.
- **Correo**: envío automático al guardar, con el PDF adjunto y las fotos incrustadas.
- **Reenvío** de la orden desde la ficha.
- **Modo sin SMTP**: si aún no configuras correo, el mensaje se guarda en `data/outbox/*.eml`.

## Probarla en tu PC

```powershell
cd "C:\Users\Admin\Documents\Default Project\ordenes_rack"
python app.py
```

Abre <http://localhost:8001>. Desde el celular, en la misma red:
`http://IP-DEL-PC:8001`.

También puedes usar `iniciar.bat`.

### Primer ingreso

- Correo: `admin@ordenes.local`
- Clave: `Admin1234`

Se crean solo la primera vez. Cámbialos en **Usuarios** y define
`ADMIN_EMAIL` / `ADMIN_PASSWORD` antes del primer arranque en producción.

### Orden de los pasos

1. **Clientes** → crear cliente.
2. **Proyectos** → asignar cliente, sitio, racks y correos destinatarios.
3. **Usuarios** → crear técnicos.
4. **Configuración** → datos de la empresa, logo y SMTP.
5. **Nueva orden** → completar, firmar y enviar.

## Configurar el correo (SMTP)

| Proveedor | Servidor | Puerto | Seguridad |
|:---|:---|:---:|:---|
| Gmail / Google Workspace | `smtp.gmail.com` | 587 | STARTTLS |
| Microsoft 365 | `smtp.office365.com` | 587 | STARTTLS |
| Zoho | `smtp.zoho.com` | 465 | SSL |
| Hosting cPanel | `mail.tudominio.cl` | 465 | SSL |

**Gmail** exige una **contraseña de aplicación** (16 caracteres), no la clave normal:
Cuenta de Google → Seguridad → Verificación en 2 pasos → Contraseñas de aplicaciones.

Usa **Probar el correo** en Configuración para validar antes de enviar una orden real.

## Publicarla en la nube

El repositorio ya está preparado: `Dockerfile`, `render.yaml` (Render) y `railway.toml`
(Railway). El servicio escucha en el puerto que entregue la plataforma y expone
`/salud` para el chequeo de estado.

### Antes de subir

1. Crea un repositorio **nuevo y vacío** en GitHub (solo para esta app).
2. Desde esta carpeta:

```powershell
git remote add origin https://github.com/TU-USUARIO/ordenes-rack.git
git push -u origin main
```

La carpeta `data/` está excluida: la base, fotos y PDF no se suben a GitHub.

### Opción A — Render (recomendada, con disco persistente)

1. En Render: **New → Blueprint** y selecciona el repositorio (usa `render.yaml`).
2. Define las variables secretas `ADMIN_EMAIL` y `ADMIN_PASSWORD`.
3. Plan **Starter**: el plan gratuito no permite discos persistentes y las fotos se
   perderían en cada despliegue.
4. Espera el deploy y abre la URL `https://TU-APP.onrender.com`.
5. Ingresa con el correo/clave definidos y cambia la clave en **Usuarios**.

### Opción B — Railway

1. **New Project → Deploy from GitHub** y elige el repositorio.
2. Agrega un **Volume** montado en `/data`.
3. Variables: `SECRET_KEY`, `DATA_DIR=/data`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`,
   `COMPANY_NAME`, `FORCE_HTTPS=1`.
4. Railway detecta el `Dockerfile` y publica con HTTPS.

### Opción C — VPS propio (Docker)

```bash
docker build -t ordenes-rack .
docker run -d --name ordenes \
  -p 80:8000 \
  -v /srv/ordenes:/data \
  -e SECRET_KEY="una-clave-larga-y-unica" \
  -e DATA_DIR=/data \
  -e ADMIN_EMAIL="admin@miempresa.cl" \
  -e ADMIN_PASSWORD="ClaveSegura123" \
  -e COMPANY_NAME="Mi Empresa SpA" \
  -e FORCE_HTTPS=1 \
  ordenes-rack
```

Ponlo detrás de Caddy/Nginx para HTTPS.

## Datos y respaldos

Todo se guarda en `DATA_DIR` (por defecto `./data`):

```
data/
├── app.db          base SQLite (clientes, proyectos, usuarios, órdenes)
├── uploads/        fotos y firmas, por código de orden
├── pdfs/           PDF generado de cada orden
├── outbox/         correos .eml cuando no hay SMTP
└── logo.png        logo de la empresa
```

Respaldo = copiar esa carpeta. En la nube, el volumen debe estar montado en `/data`.

## Seguridad

- Contraseñas con hash PBKDF2 (`werkzeug`).
- CSRF en todos los formularios.
- Sesión con cookie `HttpOnly` y `SameSite=Lax`; `Secure` con `FORCE_HTTPS=1`.
- Bloqueo temporal tras 10 intentos fallidos de login por IP.
- Fotos y PDF solo se sirven a usuarios autenticados con permiso sobre la orden.

Antes de producción:

1. Define `SECRET_KEY` larga y aleatoria.
2. Cambia la clave del administrador.
3. Usa HTTPS (`FORCE_HTTPS=1`).
4. Programa respaldos de `DATA_DIR`.

## Estructura

```
app.py            rutas, autenticación, altas y envío
db.py             SQLite y utilidades
pdf.py            documento PDF
mailer.py         armado y envío del correo
constants.py      checklist y tipos de servicio
templates/        vistas
static/           CSS, JS y manifest
```

## Límites conocidos

- El correo se envía de forma síncrona al guardar: con fotos pesadas puede tardar unos segundos.
- No hay recuperación de contraseña por correo; el administrador la restablece.
- Una orden no se edita después de enviada (sí se puede reenviar). Si necesitas corrección,
  se agrega una nota o se crea una nueva orden.
