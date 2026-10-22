-- Resumen de episodios: cuántos, a dónde van y cuánto duran (agregado).
-- @include _episodios.sql
, ep_ord AS (
  SELECT ep.*,
         MAX(fin_urg) OVER (PARTITION BY person_id ORDER BY ini
                            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS fin_urg_previo
  FROM ep
)
SELECT 'urgencias' AS origen, destino,
       COUNT(*) AS n,
       PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY min_urg) AS p25_min_urg,
       PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY min_urg) AS p50_min_urg,
       PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY min_urg) AS p75_min_urg,
       PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY min_urg) AS p90_min_urg,
       AVG((min_urg = 0)::int)             AS p_urg_cero,
       AVG((min_urg > 1440)::int)          AS p_urg_mas_24h,
       PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY min_hosp) AS p50_min_hosp,
       PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY min_hosp) AS p90_min_hosp,
       NULL::float                         AS p_tras_urgencia_48h,
       AVG(n_seg)                          AS seg_promedio
FROM epu
GROUP BY destino
UNION ALL
-- Hospitalizaciones que NO empiezan en urgencias (o que llegaron con un hueco > 1 h):
-- p_tras_urgencia_48h = proporción que empieza dentro de las 48 h siguientes al fin
-- de un episodio de urgencias del mismo paciente (sensibilidad del umbral de corte).
SELECT 'hospitalizacion_sin_urgencia_previa', 'hospitalizado',
       COUNT(*), NULL, NULL, NULL, NULL, NULL, NULL,
       PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (fin_hosp - ini_hosp)) / 60.0),
       PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (fin_hosp - ini_hosp)) / 60.0),
       AVG(COALESCE((ini - fin_urg_previo <= interval '48 hours')::int, 0)),
       AVG(n_seg)
FROM ep_ord
WHERE primer_cid = 9201;
