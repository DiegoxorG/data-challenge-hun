# Pronóstico de llegadas a urgencias

Modelo predictivo del reto (20 % de la nota). Toma las series que deja `series_tiempo`, entrena, se evalúa con backtest y pronostica los próximos días **por hora**, con intervalo. Deja tablas listas para Power BI.

## Cómo se corre

```powershell
python -m series_tiempo                 # (si no lo has corrido) arma las series en DATA_DIR\series_tiempo
python -m pronostico                    # entrena, evalúa y pronostica (no se conecta a la base)
python -m pronostico.resumen_seguro     # lo único que se comparte con Claude (palabras, sin cifras)

python -m pytest pronostico/tests       # tests con datos inventados
```

Opciones: `--horizonte-dias 14` (días a pronosticar), `--semanas-backtest 12`, `--series llegadas llegadas_hospitalizan`, `--salida`, `--series-dir`.

## Los modelos

| Modelo | Qué hace | Para qué está |
|---|---|---|
| `naive_semanal` | La misma hora de la semana pasada | Línea base: cualquier modelo serio tiene que ganarle |
| `promedio_semanal` | Promedio de esa hora de la semana en las últimas 4 semanas | Línea base más fuerte |
| `glm` | Regresión de conteos (Poisson; intervalos con binomial negativa si hay sobredispersión) | **El modelo principal** |

Variables del GLM:
- **Hora de la semana** (168 niveles): el ciclo día × hora completo.
- **Festivo × hora del día**: un festivo tiene su propio perfil (parecido a un domingo).
- **Calendario colombiano**: día después de festivo, puente, Semana Santa, Carnaval y 24 dic-1 ene (de `series_tiempo.calendario`).
- **Estacionalidad anual**: 2 armónicos de Fourier. Solo entran con 2 años o más de historia; con menos se confunden con la tendencia.
- **Tendencia lineal**: en años.

**¿Por qué un GLM y no SARIMA o Prophet?**
- Los conteos por hora son pequeños y nunca negativos, y eso es justo lo que modela una Poisson.
- El ciclo dominante dura 168 h, demasiado largo para un SARIMA horario.
- Cada coeficiente se lee directo: "un festivo multiplica las llegadas por X".
- Es rápido, así que el backtest de varias semanas corre en segundos.

**Evaluación (backtest rodante):** se corta en una fecha, se entrena solo con lo anterior y se pronostica la semana siguiente; luego se avanza una semana y se repite. Se reporta:
- MAE y RMSE por hora, y MAE y MAPE por día.
- El sesgo.
- El **MASE** (error ÷ error de la naive; menor que 1 significa que le gana).
- La cobertura del intervalo del 90 %, por hora y por día.

Solo entran horas `completo`: los meses incompletos de 2026 no se usan ni para entrenar ni para evaluar.

## Tablas para Power BI (`DATA_DIR\pronostico\powerbi`)

Son información derivada de los datos del HUN: se quedan en el computador, nunca van a git ni a la nube. El dashboard se guarda como `.pbit`.

| Archivo | Una fila por | Columnas | Para qué visual |
|---|---|---|---|
| `pronostico_horario.csv` | serie × hora | `serie, hora, real, pred, li, ls, tipo, fecha, dia_semana, hora_dia` | Línea real vs predicho por hora. `tipo`: `historico` (real + ajuste del modelo) o `futuro` (pronóstico con intervalo `li`-`ls`) |
| `pronostico_diario.csv` | serie × día | `serie, tipo, fecha, real, pred, li, ls` | Línea diaria con banda de confianza en el futuro |
| `backtest_horario.csv` | serie × modelo × semana de prueba × hora | `serie, hora, corte, modelo, real, pred, li, ls, ...` | "Así le fue al modelo en semanas que no vio" (lo honesto para el jurado) |
| `backtest_diario.csv` | serie × modelo × corte × día | `serie, modelo, corte, fecha, real, pred` | Comparación de modelos por día |
| `metricas_modelos.csv` | serie × modelo | `mae_hora, rmse_hora, sesgo_hora, mase_hora, mae_dia, mape_dia, mase_dia, cobertura_intervalo, cobertura_intervalo_dia` | Tabla o tarjetas: cuánto le gana el GLM a las líneas base |
| `efectos_calendario.csv` | serie × efecto | `efecto, multiplicador` (1.10 = 10 % más llegadas) | Barras: efecto de festivos y temporadas |
| `perfil_semana.csv` | serie × día × hora | `dia_semana (0 = lunes), hora_dia, relativo` (1.5 = 50 % más que la hora promedio) | Heatmap día × hora del modelo |

Series: `llegadas` (todas las llegadas a urgencias) y `llegadas_hospitalizan` (las que terminan en cama, para planear camas).

## Cómo se conecta con la optimización

- El perfil y el pronóstico por hora dicen **cuándo** viene la carga: así se refuerzan personal y cubículos en las franjas pico antes de que lleguen.
- `llegadas_hospitalizan` dice cuántas camas se van a pedir desde urgencias en cada franja: si se gestionan las altas de cama antes de esa hora, baja la espera de cama dentro de urgencias, que es el cuello de botella principal.
- Con la ley de Little (gente adentro = llegadas × tiempo de estancia), el pronóstico de llegadas se convierte en ocupación esperada de urgencias para los escenarios.
