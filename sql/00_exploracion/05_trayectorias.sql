-- Rutas de etapas más frecuentes (para el Sankey). Agregado por ruta, no por paciente.
-- schema: uninorte_omop
WITH rutas AS (
  SELECT vd.visit_occurrence_id,
         STRING_AGG(c.concept_name, ' > ' ORDER BY vd.visit_detail_start_datetime) AS ruta
  FROM visit_detail vd
  JOIN concept c ON c.concept_id = vd.visit_detail_concept_id
  GROUP BY 1
)
SELECT ruta, COUNT(*) AS visitas
FROM rutas
GROUP BY ruta
ORDER BY visitas DESC
LIMIT 200;
