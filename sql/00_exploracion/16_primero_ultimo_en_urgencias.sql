-- En visitas que pasan por urgencias (9203 o 3045729): ¿qué segmento va primero y cuál último?
WITH urg AS (
  SELECT DISTINCT visit_occurrence_id
  FROM visit_detail
  WHERE visit_detail_concept_id IN (9203, 3045729)
), s AS (
  SELECT vd.visit_occurrence_id,
         vd.visit_detail_concept_id AS cid,
         ROW_NUMBER() OVER (PARTITION BY vd.visit_occurrence_id
                            ORDER BY vd.visit_detail_start_datetime, vd.visit_detail_id) AS rn,
         COUNT(*)     OVER (PARTITION BY vd.visit_occurrence_id) AS tot
  FROM visit_detail vd
  JOIN urg u ON u.visit_occurrence_id = vd.visit_occurrence_id
)
SELECT 'primero' AS posicion, c.concept_name AS segmento, COUNT(*) AS n
FROM s JOIN concept c ON c.concept_id = s.cid WHERE rn = 1 GROUP BY 1, 2
UNION ALL
SELECT 'ultimo', c.concept_name, COUNT(*)
FROM s JOIN concept c ON c.concept_id = s.cid WHERE rn = tot GROUP BY 1, 2
ORDER BY posicion, n DESC;