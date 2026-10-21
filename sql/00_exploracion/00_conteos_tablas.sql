-- Cuántos registros hay por tabla (solo conteos, sin datos de pacientes).
-- schema: uninorte_omop
SELECT 'person' AS tabla, COUNT(*) AS n FROM person
UNION ALL SELECT 'visit_occurrence', COUNT(*) FROM visit_occurrence
UNION ALL SELECT 'visit_detail', COUNT(*) FROM visit_detail
UNION ALL SELECT 'condition_occurrence', COUNT(*) FROM condition_occurrence
UNION ALL SELECT 'procedure_occurrence', COUNT(*) FROM procedure_occurrence
UNION ALL SELECT 'measurement', COUNT(*) FROM measurement
UNION ALL SELECT 'concept', COUNT(*) FROM concept;
