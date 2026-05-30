# Telegram Tracker Light App

Aplicacion local para descargar, actualizar, buscar y analizar mensajes de canales de Telegram usando la API oficial de Telegram y Telethon.

Este proyecto es una adaptacion de:

- [congosto/telegram-tracker-light](https://github.com/congosto/telegram-tracker-light), de Mari Luz Congosto: [https://github.com/congosto](https://github.com/congosto)
- [estebanpdl/telegram-tracker](https://github.com/estebanpdl/telegram-tracker), de Esteban Ponce de Leon: [https://github.com/estebanpdl](https://github.com/estebanpdl)

La adaptacion empaqueta el flujo en una app local con interfaz grafica, incorpora busqueda por terminos, deteccion de indicadores de pago, generacion de dashboards/graficos y descubrimiento de canales similares.

## Que permite hacer

- Configurar credenciales de Telegram sin editar archivos a mano.
- Descargar mensajes de un canal.
- Crear datasets a partir de listas de canales.
- Actualizar canales ya descargados evitando duplicados.
- Buscar mensajes por terminos en un canal o en una lista de canales.
- Generar graficos y dashboards HTML.
- Construir redes de forwards y redes de canales similares en formato GEXF/GraphML.
- Detectar IOCs de metodos de pago: BTC, ETH/EVM, TRON/USDT, LTC, BCH, XMR, IBAN, PayPal y telefonos tipo Bizum con contexto de pago.

## Estructura del entregable

```text
telegram-tracker-light-app/
  app.py
  README.md
  requirements.txt
  config/
    config.example.ini
    config.ini              # generado por el usuario; no compartir con credenciales reales
  scripts/
    api/
    utils/
    main.py
    setup.py
    login.py
    menu.py
    build-dataset.py
    search_messages.py
    similar_channels.py
    draw_charts.py
    dashboard.py
    filtrobtc.py
    net.py
    summary_channels.py
    summary_datasets.py
    update_channels.py
    start_app.bat
```

Las carpetas `data/` y `dataset/` se crean automaticamente al configurar o usar la aplicacion.

## Requisitos

- Windows, macOS o Linux.
- Python 3.10 o superior recomendado.
- Una cuenta de Telegram.
- Credenciales `api_id` y `api_hash` de Telegram.

En Windows, durante la instalacion de Python, marca la casilla **Add Python to PATH**.

## Instalacion rapida

Abre una terminal en la carpeta del proyecto.

En Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python app.py
```

Si PowerShell no permite activar el entorno por la politica de ejecucion, puedes usar:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

O ejecutar directamente:

```powershell
.\.venv\Scripts\python.exe app.py
```

En macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python app.py
```

## Obtener api_id y api_hash de Telegram

Esta herramienta usa la API de usuario de Telegram, no un bot de BotFather. Necesitas `api_id` y `api_hash`, que se obtienen en el portal oficial de Telegram.

Enlace oficial:

[https://my.telegram.org/auth?to=apps](https://my.telegram.org/auth?to=apps)

Segun la documentacion oficial de Telegram, para obtener un API ID debes iniciar sesion en `my.telegram.org`, entrar en **API development tools**, rellenar el formulario de aplicacion y copiar los parametros `api_id` y `api_hash`.

Pasos detallados:

1. Abre [https://my.telegram.org/auth?to=apps](https://my.telegram.org/auth?to=apps).
2. Escribe tu numero de telefono con prefijo internacional, por ejemplo `+34123456789`.
3. Telegram enviara un codigo de confirmacion a tu aplicacion de Telegram.
4. Introduce el codigo en la web.
5. Entra en **API development tools**.
6. Si no tienes aplicacion creada, completa el formulario:
   - `App title`: nombre descriptivo, por ejemplo `Telegram Tracker Local`.
   - `Short name`: nombre corto, por ejemplo `trackerlocal`.
   - `Platform`: Desktop o la opcion mas parecida a tu uso.
   - `Description`: indica que es una herramienta local de analisis con la API de Telegram.
7. Guarda el formulario.
8. Copia:
   - `api_id`
   - `api_hash`
9. Abre la app (`python app.py`) y pega esos datos en la pestana **Configuracion**.

Representacion orientativa de la pagina:

```text
my.telegram.org
┌────────────────────────────────────────────┐
│ Your Telegram Core                         │
│                                            │
│  API development tools  ← entra aqui       │
│  Delete account                            │
│  Log out                                   │
└────────────────────────────────────────────┘
```

Despues de crear la aplicacion veras algo similar a:

```text
App api_id:   1234567
App api_hash: abcdef1234567890abcdef1234567890
```

Guarda esos valores solo en tu copia local. No publiques `config/config.ini`.

## Primer arranque

Ejecuta:

```powershell
python app.py
```

O en Windows, si prefieres un lanzador:

```powershell
.\scripts\start_app.bat
```

En la app:

1. Abre la pestana **Configuracion**.
2. Pulsa **Abrir pagina de Telegram** si aun no tienes credenciales.
3. Introduce `api_id`, `api_hash` y telefono.
4. Pulsa **Guardar configuracion**.
5. Pulsa **Autorizar sesion** la primera vez que uses la cuenta.
6. Si Telegram solicita un codigo, escribelo en **Codigo Telegram (si lo solicita)** y pulsa **Enviar codigo**.
7. Ve a **Captura** o **Buscar por termino**.

La app guarda las credenciales en:

```text
config/config.ini
```

Tambien existe una plantilla sin secretos:

```text
config/config.example.ini
```

## Uso desde la app

### Configuracion

Permite guardar:

- `api_id`
- `api_hash`
- telefono con prefijo internacional

Tambien permite autorizar la sesion de Telegram. Si la consola indica que se ha enviado un codigo, usa el campo **Codigo Telegram (si lo solicita)**. La zona inferior **Entrada a consola** sirve para responder a cualquier otra pregunta interactiva del proceso en ejecucion.

### Captura

Opciones:

- Descargar un canal.
- Crear un dataset desde un archivo con una lista de canales.
- Crear un dataset snowball usando los canales relacionados detectados al descargar un canal raiz.

El archivo de lista debe contener un canal por linea:

```text
canaluno
canaldos
otrocanal
```

La opcion **Crear dataset snowball** parte de un canal ya descargado. Al descargar un canal, la herramienta genera:

```text
data/<canal>/related_channels.csv
```

Ese archivo se usa como lista de entrada para crear un nuevo dataset, por defecto:

```text
dataset/<canal>_n2/
```

Flujo recomendado:

1. Descargar primero el canal raiz.
2. Comprobar que existe `data/<canal>/related_channels.csv`.
3. Usar **Crear dataset snowball**.
4. Elegir nombre de dataset o dejar el valor por defecto `<canal>_n2`.

### Buscar por termino

Permite buscar mensajes en tiempo real sobre una lista de canales.

Campos:

- Nombre del dataset donde se guardaran los resultados.
- Terminos de busqueda.
- Lista de canales en archivo `.txt` o `.csv`, un canal por linea.

Los terminos pueden separarse con comas o con `OR`:

```text
bitcoin, paypal
```

```text
"frase exacta" OR transferencia
```

Los resultados se guardan en `dataset/<dataset>/msgs_dataset.csv`, con la misma estructura de cabeceras que los datasets descargados por `main.py`.

### Analisis

Permite:

- Generar graficos.
- Generar dashboard HTML.
- Buscar IOCs de pago.
- Generar red GEXF de forwards.

Los graficos se generan en formato 1920x1080, con paleta pastel y fuente Century Gothic si esta disponible en el sistema.

### Canales similares

Construye una red de recomendaciones de canales a partir de un canal semilla.

Genera:

```text
similar_channels.csv
channel_recommendations_edges.csv
channel_recommendations_events.csv
channel_recommendations.gexf
channel_recommendations.graphml
```

Los archivos `.gexf` y `.graphml` pueden abrirse en Gephi u otras herramientas de analisis de redes.

## Salidas generadas

### Canal individual

```text
data/<canal>/
  msgs_dataset.csv
  collected_chats.csv
  collected_chats_full.csv
  related_channels.csv
  counter.csv
  context/
```

### Dataset

```text
dataset/<dataset>/
  msgs_dataset.csv
  collected_chats.csv
  channel_list.csv
  context/
  images/
  dashboard.html
  payment_iocs.csv
```

## Uso por terminal

La interfaz grafica es la forma recomendada, pero tambien pueden ejecutarse scripts directamente.

Configurar credenciales:

```powershell
python scripts/setup.py
```

Autorizar sesion de Telegram:

```powershell
python scripts/login.py
```

Descargar canal:

```powershell
python scripts/main.py --telegram-channel nombrecanal
```

Crear dataset desde lista:

```powershell
python scripts/build-dataset.py --dataset-name midataset --channel-list canales.txt
```

Crear dataset snowball desde un canal ya descargado:

```powershell
python scripts/build-dataset.py --dataset-name canalraiz_n2 --channel-list data/canalraiz/related_channels.csv
```

Buscar terminos en una lista:

```powershell
python scripts/search_messages.py --terms "Rita OR Maestre" --dataset-name busqueda_rita --channel-list canales.txt
```

Detectar IOCs en un dataset:

```powershell
python scripts/filtrobtc.py --dataset midataset
```

Descubrir canales similares:

```powershell
python scripts/similar_channels.py --telegram-channel nombrecanal --profundidad 2 --dataset-name nombrecanal_similar
```

## Seguridad y privacidad

- No compartas `config/config.ini`.
- No compartas archivos `.session`.
- No subas datasets con mensajes privados o sensibles sin revisar su contenido.
- Esta herramienta usa una cuenta de Telegram real, por lo que debes respetar los terminos de uso de Telegram y la legislacion aplicable.
- Evita lanzar descargas masivas sin necesidad: algunos canales pueden tener millones de mensajes y la API puede aplicar esperas por rate limit.

## Solucion de problemas

### `ModuleNotFoundError`

Instala dependencias:

```powershell
pip install -r requirements.txt
```

### Telegram pide codigo en el primer uso

Es normal. Telethon pedira el codigo que Telegram envia a tu aplicacion. Tras iniciar sesion se crea una sesion local para no repetir el login constantemente.

### `api_id` debe ser numerico

El `api_id` no es el `api_hash`. El primero es un numero; el segundo es una cadena larga.

### No aparecen graficos

Comprueba que existe:

```text
dataset/<dataset>/msgs_dataset.csv
```

o:

```text
data/<canal>/msgs_dataset.csv
```

### Problemas con WordCloud o NLTK

La primera ejecucion puede descargar recursos de stopwords de NLTK. Si no hay conexion, ejecuta la generacion de graficos cuando haya acceso a internet.

## Notas de credito

Este entregable mantiene la base conceptual y funcional de `telegram-tracker` y `telegram-tracker-light`: descarga con Telethon, datasets CSV, contexto de descarga, actualizacion incremental y analisis posterior. La capa de app local, busqueda por terminos, deteccion de IOCs, ordenacion de scripts y flujo de entrega se han anadido como adaptacion para uso guiado y demostraciones.
