-- Llegadas a urgencias por DÍA y por grupo (agregado). Formato largo: fecha, dimensión, grupo,
-- llegadas. Los días sin llegadas en un grupo no aparecen; series_tiempo los rellena con 0.
--   sexo      gender_concept_id de person (nombre del concepto)
--   edad      edad al llegar = año de llegada − año de nacimiento, en grupos
--   destino   alta / hospitalizado
-- @include _episodios.sql
, base AS (
  SELECT e.llegada::date AS fecha, e.destino,
         COALESCE(cg.concept_name, 'sin dato') AS sexo,
         EXTRACT(YEAR FROM e.llegada)::int - p.year_of_birth AS edad
  FROM epu e
  LEFT JOIN person p   ON p.person_id = e.person_id
  LEFT JOIN concept cg ON cg.concept_id = p.gender_concept_id
)
SELECT fecha, 'sexo' AS dimension, sexo AS grupo, COUNT(*) AS llegadas FROM base GROUP BY 1, 3
UNION ALL
SELECT fecha, 'edad',
       CASE WHEN edad IS NULL OR edad < 0 OR edad > 110 THEN 'sin dato'
            WHEN edad < 5 THEN '0-4' WHEN edad < 18 THEN '5-17' WHEN edad < 45 THEN '18-44'
            WHEN edad < 65 THEN '45-64' ELSE '65+' END,
       COUNT(*)
FROM base GROUP BY 1, 3
UNION ALL
SELECT fecha, 'destino', destino, COUNT(*) FROM base GROUP BY 1, 3
ORDER BY 1, 2, 3;
