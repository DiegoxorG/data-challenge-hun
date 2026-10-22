# Metodología: reconstrucción de episodios de urgencias

## Por qué no usamos `visit_occurrence` directamente

La exploración (consultas `sql/00_exploracion/11` a `18`) mostró que en la base del HUN:

- `visit_occurrence` casi siempre tiene la misma hora de inicio y de fin, así que no sirve para medir duraciones.
- Una misma `visit_occurrence` agrupa segmentos separados por días (por ejemplo, un evento ambulatorio y, días después, una urgencia). No equivale a un episodio de atención.
- Las duraciones reales están en `visit_detail`.

## Cómo está registrado el paso por urgencias

| Concepto | Qué representa en esta base | Duración típica |
|---|---|---|
| 9203 Emergency Room Visit | Marca de llegada/registro | 0 o menos de 15 min, solapada con el inicio de la atención |
| 3045729 Treatment urgency | Estancia en urgencias (atención/observación) | 1–4 h, con cola larga; varios segmentos seguidos |
| 9201 Inpatient Visit | Hospitalización | 1–7 días |
| 581479 Ambulatory Rehabilitation Visit | Eventos ambulatorios puntuales | 0 (fuera del flujo de urgencias) |

El uso de 3045729 como tipo de visita y de segmento es propio del mapeo del HUN (en OMOP estándar es un concepto de observación). Está pendiente confirmarlo con los organizadores.

## Definición de episodio

Implementada en `sql/01_episodios/_episodios.sql`:

1. Se toman los segmentos de `visit_detail` con conceptos 9203, 3045729 y 9201, y se asocian al paciente vía `visit_occurrence`.
2. Por paciente y en orden cronológico, un segmento **continúa** el episodio si empieza antes de que termine lo anterior o con un hueco de hasta `gap_min` minutos (60 por defecto). Si el hueco es mayor, empieza un episodio nuevo (técnica *gaps and islands*).
3. Para cada episodio:
   - **Llegada** = primer inicio de un segmento de urgencias (9203 o 3045729).
   - **Fin de urgencias** = último fin de un segmento de urgencias.
   - **Destino** = `hospitalizado` si el episodio incluye 9201; si no, `alta`.
   - **Tiempo en urgencias** = fin de urgencias − llegada.
   - **Estancia hospitalaria** = último fin de 9201 − primer inicio de 9201.
4. Los episodios que empiezan en hospitalización (sin urgencia previa contigua) se tratan aparte.

## Interpretación clave

En la mayoría de los casos, el registro de urgencias termina exactamente cuando empieza la hospitalización. Por eso **la espera de cama (boarding) queda dentro del tiempo en urgencias** de los pacientes hospitalizados. La diferencia entre el tiempo en urgencias de hospitalizados y de dados de alta es un indicador del bloqueo por falta de camas.

## Ocupación hora a hora

`sql/01_episodios/23_ocupacion_por_hora.sql` calcula el censo al cierre de cada hora (entradas acumuladas − salidas acumuladas), para urgencias (llegada → fin de urgencias) y hospitalización (todas las estancias con 9201). Los primeros días de la serie subestiman la ocupación porque no cuentan a quienes ya estaban adentro; se descartan como calentamiento.

## Limitaciones

- No hay nivel de triaje (I–V) ni etapas internas de urgencias (triaje, admisión, consulta).
- `procedure_occurrence` solo tiene fecha (sin hora).
- El umbral de 60 min es una decisión de modelado. `20_resumen_episodios.sql` reporta qué parte de las hospitalizaciones "sin urgencia previa" empieza dentro de las 48 h siguientes a una urgencia, como chequeo de sensibilidad.
- Capacidades de referencia (58 cubículos, 64 camas) tomadas de la visita de campo del 1 de octubre; por confirmar.

## Datos sintéticos

`scripts/generar_sintetico.py` crea en un PostgreSQL **local** una base inventada con esta misma estructura, para desarrollar y probar sin acceder a la base del HUN. Se niega a escribir en un host que no sea local.