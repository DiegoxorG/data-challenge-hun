-- Qué se mide en measurement y cuántos registros traen texto fuente
SELECT c.concept_id, c.concept_name,
       COUNT(*) AS n,
       COUNT(m.measurement_source_value_extended) AS con_texto
FROM measurement m
LEFT JOIN concept c ON c.concept_id = m.measurement_concept_id
GROUP BY 1, 2
ORDER BY n DESC
LIMIT 100;