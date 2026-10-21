-- Pares de segmentos consecutivos dentro de una visita y el hueco entre ellos
-- (inicio del siguiente - fin del actual), en franjas. Agregado.
WITH s AS (
  SELECT vd.visit_detail_concept_id AS cid,
         vd.visit_detail_end_datetime AS fin,
         LEAD(vd.visit_detail_concept_id)   OVER w AS next_cid,
         LEAD(vd.visit_detail_start_datetime) OVER w AS next_ini
  FROM visit_detail vd
  WINDOW w AS (PARTITION BY vd.visit_occurrence_id
               ORDER BY vd.visit_detail_start_datetime, vd.visit_detail_id)
), g AS (
  SELECT cid, next_cid, EXTRACT(EPOCH FROM (next_ini - fin)) / 60.0 AS hueco
  FROM s WHERE next_cid IS NOT NULL
)
SELECT ca.concept_name AS desde, cb.concept_name AS hacia,
       COUNT(*) AS n,
       AVG((hueco < 0)::int)                      AS p_solapado,
       AVG((hueco = 0)::int)                      AS p_seguido,
       AVG((hueco > 0 AND hueco < 60)::int)       AS p_hueco_menos_1h,
       AVG((hueco >= 60 AND hueco < 360)::int)    AS p_hueco_1_6h,
       AVG((hueco >= 360 AND hueco < 1440)::int)  AS p_hueco_6_24h,
       AVG((hueco >= 1440)::int)                  AS p_hueco_mas_1dia
FROM g
JOIN concept ca ON ca.concept_id = g.cid
JOIN concept cb ON cb.concept_id = g.next_cid
GROUP BY 1, 2
ORDER BY n DESC;