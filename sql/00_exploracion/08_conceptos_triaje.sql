-- Conceptos del vocabulario que podrían ser triaje (solo nombres, sin pacientes)
SELECT concept_id, concept_name, domain_id, vocabulary_id
FROM concept
WHERE concept_name ILIKE ANY (ARRAY['%triag%','%triaj%','%clasif%','%prioridad%','%urgenc%'])
ORDER BY domain_id, concept_name;