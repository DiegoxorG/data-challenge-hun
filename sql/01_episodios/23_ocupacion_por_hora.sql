-- Censo hora a hora: pacientes presentes en urgencias y en hospitalización al cierre
-- de cada hora (entradas acumuladas - salidas acumuladas). Agregado.
-- Urgencias: desde la llegada hasta el fin del último segmento de urgencias.
-- Hospitalización: todos los episodios con cama (vengan o no de urgencias).
-- @include _episodios.sql
, eventos AS (
  SELECT date_trunc('hour', llegada) AS h,  1 AS d_urg, 0 AS d_hosp FROM epu
  UNION ALL
  SELECT date_trunc('hour', fin_urg),      -1, 0 FROM epu
  UNION ALL
  SELECT date_trunc('hour', ini_hosp),      0, 1 FROM ep WHERE ini_hosp IS NOT NULL
  UNION ALL
  SELECT date_trunc('hour', fin_hosp),      0, -1 FROM ep WHERE ini_hosp IS NOT NULL
),
por_hora AS (
  SELECT h, SUM(d_urg) AS d_urg, SUM(d_hosp) AS d_hosp FROM eventos GROUP BY h
),
rango AS (
  SELECT generate_series(r.a, r.b, interval '1 hour') AS h
  FROM (SELECT MIN(h) AS a, MAX(h) AS b FROM por_hora) r
)
SELECT rango.h AS hora,
       SUM(COALESCE(p.d_urg, 0))  OVER (ORDER BY rango.h) AS en_urgencias,
       SUM(COALESCE(p.d_hosp, 0)) OVER (ORDER BY rango.h) AS en_hospitalizacion
FROM rango
LEFT JOIN por_hora p ON p.h = rango.h
ORDER BY 1;
