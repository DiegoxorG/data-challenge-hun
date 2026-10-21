# Dashboard Power BI

Aquí va el dashboard como **plantilla `.pbit`** o como **proyecto PBIP** (formato de texto, amigable con git). Nunca un `.pbix`: guarda los datos importados dentro del archivo, y el hook lo bloquea.

- `.pbit`: Archivo → Exportar → Plantilla de Power BI. Al abrirla pide los parámetros de conexión y recarga los datos desde la BD.
- PBIP: Archivo → Guardar como → Proyecto de Power BI (.pbip). La carpeta `.pbi/cache.abf` (datos) está en `.gitignore`.
- Las medidas DAX importantes se pueden copiar también a `dashboard/medidas.dax` para revisarlas en los PR.
