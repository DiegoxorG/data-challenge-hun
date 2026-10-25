# Series de tiempo: gráficas exploratorias para el pronóstico

Arma, en un solo comando, las gráficas exploratorias (EDA) de las series de urgencias y deja las series limpias, listas para que Sebastián construya el modelo sin tener que escribir SQL ni limpiar nada. No ajusta ni recomienda modelos: eso queda a criterio de quien modele.

## Cómo se corre (lo hace quien tenga VPN y `.env`)

```powershell
pip install -r requirements.txt          # agrega 'holidays' (festivos de Colombia)

python -m series_tiempo                  # consulta la base y escribe en DATA_DIR\series_tiempo
python -m series_tiempo --sin-base       # rehace el reporte con los datos de la corrida anterior
python -m series_tiempo.resumen_seguro   # lo único que se comparte con Claude (palabras, sin cifras)
```

Corre las consultas **agregadas** `sql/01_episodios/26`, `27` y `28` (una fila por hora, día o semana; ninguna por paciente). Tarda lo que tarda reconstruir los episodios, unos minutos.

## Qué deja en `DATA_DIR\series_tiempo`

| Archivo | Qué es |
|---|---|
| `reporte_series.html` | El reporte. Abre sin internet. Cada gráfica dice **qué muestra** y **cómo leerla**. |
| `datos/series_horarias.parquet` | Una fila por hora: llegadas, llegadas que se hospitalizan, contactos breves, ingresos y altas de cama, censos de urgencias y hospitalización, `completo`. |
| `datos/series_diarias.parquet` | Una fila por día: lo mismo sumado (censos como media y máximo) + calendario: día de la semana, festivo, puente, día después de festivo, Semana Santa, Carnaval, 24 dic–1 ene, `completo`. |
| `datos/llegadas_diarias_por_grupo.parquet` | Llegadas por día por sexo, grupo de edad y destino. |
| `datos/semanas_tiempos.parquet` | Mediana y p90 semanal de horas en urgencias (con y sin recorte) y días en cama, por destino; solo semanas con 10+ episodios. |
| `tablas/*.csv` | Las métricas de cada sección del reporte. |

**Todo esto es información derivada de los datos del HUN**: se queda en el computador, no va a git, a la nube ni a ninguna IA. El reporte lleva la marca `hun-datos` y el hook lo bloquea si alguien lo intenta commitear.

## Cómo se cargan las series para modelar

```python
from series_tiempo import cargar
s = cargar()                       # dict: 'horas', 'dias', 'grupos', 'semanas'
d = s["dias"]
y = d.loc[d["completo"], "llegadas"]
```

- `completo = False` marca meses incompletos y días cortados por el extracto: **no se usan para entrenar ni evaluar**.
- Para STL, ACF o SARIMA, que piden serie sin huecos: `series_tiempo.datos.tramo_continuo(d["completo"])`.

## Qué trae el reporte

| Sección | Qué muestra |
|---|---|
| A. Datos y cobertura | Rango de la serie, días completos, meses excluidos, llegadas por día con medias móviles |
| B. Nivel y tendencia | Año sobre año por mes; recta de tendencia y promedio por año |
| C. Dentro del día | Llegadas por hora; perfil del día para cada día de la semana; mapa día × hora |
| D. Semana | Llegadas por día según el día de la semana |
| E. Año | Llegadas por mes y por semana del año |
| F. Festivos y temporadas | Llegadas en festivos, puentes, Semana Santa, Carnaval de Barranquilla y fin de año frente a un día normal; días alrededor de un festivo |
| G. Descomposición | STL/MSTL diaria y horaria; fuerza de cada componente; días atípicos |
| H. Autocorrelación | ACF/PACF diaria y horaria, con y sin diferencia semanal; Ljung-Box |
| I. Estacionariedad | ADF y KPSS en nivel y con diferencias; media y desviación móviles |
| J. Distribución | Conteos por hora frente a una Poisson; varianza frente a media por franja; ceros; lambda de Box-Cox |
| K. Otras series del flujo | Ingresos y altas de cama, censos, a qué hora se liberan camas, correlación cruzada entre series |
| L. Por grupo | Llegadas por edad, sexo y destino; patrón semanal por edad |
| M. Tiempos en urgencias | Mediana semanal de la espera con y sin recorte; llegadas frente a espera |

## Notas

- **Llegadas** = episodios que empiezan en urgencias según `sql/01_episodios/_episodios.sql` (umbral de 60 min). Si el equipo cambia la definición, cambia aquí también.
- **Censos** = como la consulta 25 (urgencias cortado al ingreso a cama, sin urgencias de más de 7 días ni hospitalizaciones de más de 90). La ocupación absoluta sigue sin ser confiable hasta tener la capacidad real; los patrones sí.
- Los festivos salen del paquete `holidays` (Colombia, con la Ley Emiliani). Carnaval = sábado a martes antes del Miércoles de Ceniza; Semana Santa = Domingo de Ramos a Pascua.
- Probado con la base sintética (`scripts/generar_sintetico.py`, que ahora trae dos años con estacionalidad inventada). Tests: `python -m pytest series_tiempo/tests`; con `HUN_TEST_PG_URL` apuntando al PostgreSQL local sintético también compara la 26 contra la 21 y la 25.
