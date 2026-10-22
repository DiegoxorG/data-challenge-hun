-- ¿Se USAN los conceptos candidatos a triaje en alguna tabla? (el vocabulario los trae todos,
-- que existan en concept no significa que aparezcan en los datos)
-- 45949550 Triage level | 3119360, 3104237 Seen by triage nurse | 3045729 Treatment urgency
SELECT 'condition_occurrence' AS tabla, condition_concept_id AS concept_id, COUNT(*) AS n
FROM condition_occurrence WHERE condition_concept_id IN (45949550, 3119360, 3104237, 3045729) GROUP BY 2
UNION ALL
SELECT 'measurement', measurement_concept_id, COUNT(*)
FROM measurement WHERE measurement_concept_id IN (45949550, 3119360, 3104237, 3045729) GROUP BY 2
UNION ALL
SELECT 'visit_occurrence', visit_concept_id, COUNT(*)
FROM visit_occurrence WHERE visit_concept_id IN (45949550, 3119360, 3104237, 3045729) GROUP BY 2
UNION ALL
SELECT 'visit_detail', visit_detail_concept_id, COUNT(*)
FROM visit_detail WHERE visit_detail_concept_id IN (45949550, 3119360, 3104237, 3045729) GROUP BY 2;
