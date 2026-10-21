-- Volumen de visitas y procedimientos por año, para saber qué años cubre la data
-- (y dejar de llamarla "antes de 2024" a secas). Agregado: se puede compartir.
-- schema: uninorte_omop
SELECT EXTRACT(YEAR FROM vo.visit_start_datetime)::int AS anio,
       COUNT(*)                                       AS visitas,
       COUNT(DISTINCT vo.person_id)                   AS pacientes,
       MIN(vo.visit_start_datetime)                   AS primera,
       MAX(vo.visit_start_datetime)                   AS ultima
FROM visit_occurrence vo
GROUP BY 1
ORDER BY 1;

-- Procedimientos por año de la visita
-- SELECT EXTRACT(YEAR FROM vo.visit_start_datetime)::int AS anio, COUNT(*) AS procedimientos
-- FROM procedure_occurrence po
-- JOIN visit_occurrence vo ON po.visit_occurrence_id = vo.visit_occurrence_id
-- GROUP BY 1 ORDER BY 1;
