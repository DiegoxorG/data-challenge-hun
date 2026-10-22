-- Censo hora a hora AJUSTADO (para comparar con 23):
--  * la estancia en urgencias termina como máximo al empezar la hospitalización
--    (evita contar al mismo paciente en urgencias y en cama a la vez);
--  * se excluyen episodios de urgencias de más de 7 días y hospitalizaciones de más
--    de 90 días (probables errores de registro).
-- @include _episodios.sql
, epu_aj AS (
  SELECT llegada, LEAST(fin_urg, COALESCE(ini_hosp, fin_urg)) AS fin_urg_aj
  FROM epu
), eventos AS (
  SELECT date_trunc('hour', llegada) AS h, 1 AS d_urg, 0 AS d_hosp
  FROM epu_aj WHERE fin_urg_aj - llegada <= interval '7 days'
  UNION ALL
  SELECT date_trunc('hour', fin_urg_aj), -1, 0
  FROM epu_aj WHERE fin_urg_aj - llegada <= interval '7 days'
  UNION ALL
  SELECT date_trunc('hour', ini_hosp), 0, 1
  FROM ep WHERE ini_hosp IS NOT NULL AND fin_hosp - ini_hosp <= interval '90 days'
  UNION ALL
  SELECT date_trunc('hour', fin_hosp), 0, -1
  FROM ep WHERE ini_hosp IS NOT NULL AND fin_hosp - ini_hosp <= interval '90 days'
), por_hora AS (
  SELECT h, SUM(d_urg) AS d_urg, SUM(d_hosp) AS d_hosp FROM eventos GROUP BY h
), rango AS (
  SELECT generate_series(r.a, r.b, interval '1 hour') AS h
  FROM (SELECT MIN(h) AS a, MAX(h) AS b FROM por_hora) r
)
SELECT rango.h AS hora,
       SUM(COALESCE(p.d_urg, 0))  OVER (ORDER BY rango.h) AS en_urgencias,
       SUM(COALESCE(p.d_hosp, 0)) OVER (ORDER BY rango.h) AS en_hospitalizacion
FROM rango
LEFT JOIN por_hora p ON p.h = rango.h
ORDER BY 1;
