-- Qué tipos de visita y qué etapas (visit_detail) existen. Verificar los IDs OMOP
-- asumidos (9203 urgencias, 9201 hospitalización, 9202 consulta externa, 262 ER+IP).
-- schema: uninorte_omop
SELECT 'visit' AS nivel, c.concept_id, c.concept_name, c.vocabulary_id, COUNT(*) AS n
FROM visit_occurrence vo JOIN concept c ON c.concept_id = vo.visit_concept_id
GROUP BY 2,3,4
UNION ALL
SELECT 'detail', c.concept_id, c.concept_name, c.vocabulary_id, COUNT(*)
FROM visit_detail vd JOIN concept c ON c.concept_id = vd.visit_detail_concept_id
GROUP BY 2,3,4
ORDER BY nivel, n DESC;
