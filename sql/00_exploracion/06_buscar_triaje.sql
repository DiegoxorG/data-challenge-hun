-- ¿Dónde está el nivel de triaje? Busca conceptos con "triag" usados en
-- measurement y visit_detail (solo nombres de concepto + conteos).
-- schema: uninorte_omop
SELECT 'measurement' AS tabla, c.concept_id, c.concept_name, COUNT(*) AS n
FROM measurement m JOIN concept c ON c.concept_id = m.measurement_concept_id
WHERE c.concept_name ILIKE '%triag%'
GROUP BY 2,3
UNION ALL
SELECT 'visit_detail', c.concept_id, c.concept_name, COUNT(*)
FROM visit_detail vd JOIN concept c ON c.concept_id = vd.visit_detail_concept_id
WHERE c.concept_name ILIKE '%triag%'
GROUP BY 2,3
ORDER BY n DESC;
