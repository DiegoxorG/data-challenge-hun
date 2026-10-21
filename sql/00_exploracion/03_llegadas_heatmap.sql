-- Llegadas a urgencias por día de semana (1=lunes) y hora. Base del heatmap.
-- schema: uninorte_omop
SELECT EXTRACT(ISODOW FROM visit_start_datetime)::int AS dow,
       EXTRACT(HOUR   FROM visit_start_datetime)::int AS hora,
       COUNT(*) AS llegadas
FROM visit_occurrence
WHERE visit_concept_id IN (9203, 262)   -- verificar con 02_tipos_visita_y_etapas.sql
GROUP BY 1, 2
ORDER BY 1, 2;
