-- ¿Las horas son reales o vienen redondeadas a medianoche? ¿Hay duraciones cero o absurdas?
-- Proporciones por tipo de visita/segmento (agregado).
SELECT 'visit_occurrence' AS tabla, c.concept_name AS tipo, COUNT(*) AS n,
       AVG((vo.visit_start_datetime::time = '00:00:00')::int) AS p_inicio_medianoche,
       AVG((vo.visit_end_datetime::time   = '00:00:00')::int) AS p_fin_medianoche,
       AVG((vo.visit_end_datetime = vo.visit_start_datetime)::int) AS p_duracion_cero,
       AVG((vo.visit_end_datetime - vo.visit_start_datetime > interval '30 days')::int) AS p_mas_30_dias
FROM visit_occurrence vo JOIN concept c ON c.concept_id = vo.visit_concept_id
GROUP BY 1, 2
UNION ALL
SELECT 'visit_detail', c.concept_name, COUNT(*),
       AVG((vd.visit_detail_start_datetime::time = '00:00:00')::int),
       AVG((vd.visit_detail_end_datetime::time   = '00:00:00')::int),
       AVG((vd.visit_detail_end_datetime = vd.visit_detail_start_datetime)::int),
       AVG((vd.visit_detail_end_datetime - vd.visit_detail_start_datetime > interval '30 days')::int)
FROM visit_detail vd JOIN concept c ON c.concept_id = vd.visit_detail_concept_id
GROUP BY 1, 2;