-- Duración de cada tipo de segmento (visit_detail), en franjas. Agregado.
WITH d AS (
  SELECT vd.visit_detail_concept_id AS cid,
         EXTRACT(EPOCH FROM (vd.visit_detail_end_datetime - vd.visit_detail_start_datetime)) / 60.0 AS dur
  FROM visit_detail vd
)
SELECT c.concept_name AS segmento,
       COUNT(*) AS n,
       AVG((dur = 0)::int)                        AS p_cero,
       AVG((dur > 0 AND dur < 15)::int)           AS p_menos_15min,
       AVG((dur >= 15 AND dur < 60)::int)         AS p_15_60min,
       AVG((dur >= 60 AND dur < 240)::int)        AS p_1_4h,
       AVG((dur >= 240 AND dur < 720)::int)       AS p_4_12h,
       AVG((dur >= 720 AND dur < 1440)::int)      AS p_12_24h,
       AVG((dur >= 1440 AND dur < 10080)::int)    AS p_1_7dias,
       AVG((dur >= 10080)::int)                   AS p_mas_7dias,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY dur) FILTER (WHERE dur > 0) AS mediana_min_sin_ceros
FROM d JOIN concept c ON c.concept_id = d.cid
GROUP BY 1
ORDER BY n DESC;