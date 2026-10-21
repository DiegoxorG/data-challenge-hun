-- Qué segmentos (visit_detail) aparecen dentro de cada tipo de visita
SELECT cv.concept_name AS tipo_visita, cd.concept_name AS segmento, COUNT(*) AS n
FROM visit_detail vd
JOIN visit_occurrence vo ON vo.visit_occurrence_id = vd.visit_occurrence_id
JOIN concept cv ON cv.concept_id = vo.visit_concept_id
JOIN concept cd ON cd.concept_id = vd.visit_detail_concept_id
GROUP BY 1, 2
ORDER BY 1, n DESC;