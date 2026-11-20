# Semáforo de saturación por turno

Convierte el pronóstico horario en una **alerta temprana por turno** para los próximos 14 días: verde, amarillo o rojo, con un protocolo de acción y un responsable para cada color. Responde a lo que piden las bases del reto: "sistemas de alerta temprana" y "detectar posibles escenarios de saturación".

## Cómo se corre

```powershell
python -m pronostico --excluir-ultimas-semanas 6   # (si no lo has corrido)
python -m semaforo                                  # no se conecta a la base
python -m semaforo.resumen_seguro                   # lo único que se comparte con Claude
python -m pronostico.reporte                        # incluye el calendario del semáforo y su validación

python -m pytest semaforo/tests                     # tests con datos inventados
```

## Cómo funciona

1. **Turnos:** mañana 7-13 h, tarde 13-19 h y noche 19-7 h. La noche pertenece al día en que empieza.
2. **Qué es un turno cargado o crítico:** se calculan los percentiles 75 y 90 de las llegadas de **ese mismo turno** en las últimas 52 semanas válidas. Se usa solo el último año porque la demanda tiene tendencia, y los umbrales de años viejos no describen la operación actual.
3. **Probabilidad:** el total del turno se modela como binomial negativa, con la media del pronóstico y una dispersión estimada con los **errores del backtest a nivel de turno**, es decir, fuera de muestra. Con eso se calcula P(turno cargado) y P(turno crítico).
4. **Color, con reglas de riesgo relativo fijadas antes de ver los datos reales.** Un turno cualquiera es crítico el 10 % de las veces y cargado el 25 %.

| Color | Regla | Lectura |
|---|---|---|
| Rojo | P(crítico) ≥ 40 % | Riesgo de turno crítico 4 veces el normal |
| Amarillo | P(crítico) ≥ 20 % o P(cargado) ≥ 50 % | Riesgo 2 veces el normal |
| Verde | En otro caso | Operación normal |

5. **Protocolo:** cada color trae acciones y un responsable, distintos para urgencias (llegadas) y para camas (llegadas que se hospitalizan). Están en `calculo.PROTOCOLO`.

## Validación

El semáforo se aplica a las semanas del backtest, con pronósticos hechos sin ver esas semanas. Para que la evaluación sea honesta:
- Los umbrales se calculan solo con datos anteriores al periodo evaluado.
- La dispersión de cada semana se estima con las otras semanas (dejar una fuera).

Se compara el color con lo que pasó, y el mismo procedimiento con la naïve sirve de referencia. Métricas:

| Métrica | Pregunta que responde |
|---|---|
| `sensibilidad_critico` | De los turnos que fueron críticos, ¿cuántos tenían alerta? |
| `criticos_en_verde` | ¿Cuántos turnos críticos quedaron en verde? (el error que más importa) |
| `precision_alerta`, `precision_rojo` | De las alertas, ¿cuántas fueron turnos cargados o críticos? |
| `tasa_alerta` | ¿Qué fracción de turnos se alerta? (si todo es alerta, nadie la atiende) |
| `riesgo_critico_en_alerta` vs `riesgo_critico_en_verde` | ¿La alerta concentra el riesgo? (base ≈ 10 %) |

**Qué esperar:** el semáforo anticipa lo sistemático (lunes, festivos, temporadas, el rebote después de un festivo), y no los picos al azar ni los eventos externos. Su valor está en que sus alertas son más confiables que las de la naïve y en que llegan con días de anticipación.

## Tablas para Power BI (`DATA_DIR\semaforo\powerbi`)

| Archivo | Una fila por | Para qué visual |
|---|---|---|
| `semaforo_futuro.csv` | serie × fecha × turno | Calendario (matriz fecha × turno con color de fondo por `color`) + tarjeta con `accion` y `responsable` al seleccionar |
| `semaforo_validacion.csv` | serie × modelo × turno del backtest | Detalle: color pronosticado vs `categoria_real` |
| `semaforo_metricas.csv` | serie × modelo | Tarjetas: sensibilidad, críticos en verde, precisión, comparadas con la naïve |
| `semaforo_confusion.csv` | serie × modelo × color × categoría real | Matriz de confusión 3 × 3 |
| `umbrales.csv` | serie × turno | Qué significa "cargado" y "crítico" en cada turno |
| `protocolo.csv` | serie × color | Tabla del protocolo de acción |

Son información derivada de los datos del HUN: se quedan en el computador, nunca van a git ni a la nube.

**Nota de uso:** en operación, el semáforo se correría a diario con los datos al día. En este reto, el "futuro" son los días que siguen al último dato confiable, así que sirve para demostrar el funcionamiento; la validación es la que muestra su desempeño.
