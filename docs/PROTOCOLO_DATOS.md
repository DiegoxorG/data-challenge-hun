# Protocolo de manejo de datos del HUN

Firmamos un NDA y unos términos que prohíben subir datos del HUN a servicios en la nube, plataformas de terceros o herramientas de IA sin autorización. Hacerlo es causal de descalificación, y la confidencialidad sigue vigente después del reto. Este protocolo es cómo cumplimos eso en el día a día.

## Lo que NUNCA se hace

- Subir datos a GitHub, **aunque el repo sea privado**. GitHub es un tercero en la nube, el repo es un entregable que se comparte con los jurados, y lo que entra al historial de git queda ahí aunque después se borre el archivo.
- Guardar extractos en OneDrive, Google Drive, iCloud, Dropbox ni mandarlos por WhatsApp, correo o Discord.
- Pegar filas, tablas o capturas con datos de pacientes en Claude, ChatGPT, Copilot o cualquier IA.
- Guardar contraseñas en el código, en notebooks o en el chat del grupo.
- Usar `git commit --no-verify`.

## Lo que sí se comparte

| Se puede | Dónde |
|---|---|
| Consultas SQL, código, notebooks **sin outputs** | GitHub |
| Nombres de tablas/columnas, esquema, conceptos OMOP | GitHub, chat, IA |
| Conteos y agregados (p. ej. visitas por año, mediana por etapa) | GitHub, informe, chat |
| Gráficas de agregados | Informe, presentación |
| Datos sintéticos inventados para probar código | GitHub, IA |

Regla práctica: si una fila identifica a un paciente o a una visita concreta (person_id, visit_occurrence_id, fechas exactas de un caso), no sale del equipo autorizado. Agregados con grupos pequeños (menos de ~10 pacientes) también se tratan como sensibles.

## Cómo se comparten datos entre nosotros

No se pasan archivos. Cada integrante **corre la misma consulta** desde `sql/` con su propio usuario y obtiene el mismo extracto en su `DATA_DIR`. Así lo que viaja es el SQL, no los datos. Si una consulta tarda mucho, se acuerda quién la corre y se comparte el **resultado agregado**, no la tabla cruda.

## En el computador de cada uno

- `DATA_DIR` local, fuera del repo y de carpetas sincronizadas (el código lo valida).
- Disco cifrado: BitLocker (Windows) o FileVault (macOS).
- Credenciales solo en `.env` (ignorado por git).
- Al terminar el reto, o si los organizadores lo piden: borrar `DATA_DIR` y cualquier copia.

## Power BI

- `.pbix` lleva los datos importados adentro: **no se sube**.
- Se versiona como plantilla `.pbit` (Archivo → Exportar → Plantilla de Power BI) o como proyecto PBIP sin la carpeta de caché (`.pbi/cache.abf` está ignorada).
- El dashboard publicado se comparte por el canal que indiquen los organizadores, no por enlace público ("Publicar en la web" expone los datos a cualquiera).

## Si algo se filtró

1. No intentes arreglarlo en silencio. Avisa al grupo de inmediato.
2. Si llegó a GitHub: hacer el repo inaccesible, borrar el archivo y reescribir el historial (`git filter-repo`), y pedir a GitHub Support que purgue cachés.
3. **Reportar a los organizadores** como exigen los términos. Reportar a tiempo es mucho mejor que que lo descubran.
