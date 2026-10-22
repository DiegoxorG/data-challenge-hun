-- ¿La visita (visit_occurrence) calza con sus segmentos? Duración real de la visita
-- = primer inicio -> último fin de sus segmentos. Agregado por tipo de visita.
WITH d AS (
  SELECT visit_occurrence_id,
         MIN(visit_detail_start_datetime) AS ini,
         MAX(visit_detail_end_datetime)   AS fin
  FROM visit_detail GROUP BY 1
), v AS (
  SELECT vo.visit_concept_id AS cid,
         d.visit_occurrence_id IS NULL AS sin_segmentos,
         vo.visit_start_datetime = d.ini AS inicio_coincide,
         EXTRACT(EPOCH FROM (d.fin - d.ini)) / 60.0 AS span
  FROM visit_occurrence vo
  LEFT JOIN d ON d.visit_occurrence_id = vo.visit_occurrence_id
)
SELECT c.concept_name AS tipo_visita,
       COUNT(*) AS n,
       AVG(sin_segmentos::int)                           AS p_sin_segmentos,
       AVG(inicio_coincide::int)                         AS p_inicio_coincide,
       AVG((span = 0)::int)                              AS p_span_cero,
       AVG((span > 0 AND span < 240)::int)               AS p_span_menos_4h,
       AVG((span >= 240 AND span < 1440)::int)           AS p_span_4_24h,
       AVG((span >= 1440 AND span < 10080)::int)         AS p_span_1_7dias,
       AVG((span >= 10080)::int)                         AS p_span_mas_7dias,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY span) FILTER (WHERE span > 0) AS mediana_span_min
FROM v JOIN concept c ON c.concept_id = v.cid
GROUP BY 1
ORDER BY n DESC;
