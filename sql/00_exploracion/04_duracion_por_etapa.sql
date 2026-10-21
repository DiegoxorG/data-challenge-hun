-- Duración por etapa (minutos): mediana, p90 y registros con fechas inválidas.
-- schema: uninorte_omop
SELECT c.concept_name AS etapa,
       COUNT(*) AS n,
       COUNT(*) FILTER (WHERE vd.visit_detail_end_datetime IS NULL)                         AS sin_fin,
       COUNT(*) FILTER (WHERE vd.visit_detail_end_datetime < vd.visit_detail_start_datetime) AS fin_antes_inicio,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (vd.visit_detail_end_datetime - vd.visit_detail_start_datetime))/60) AS mediana_min,
       PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (vd.visit_detail_end_datetime - vd.visit_detail_start_datetime))/60) AS p90_min
FROM visit_detail vd
JOIN concept c ON c.concept_id = vd.visit_detail_concept_id
GROUP BY 1
ORDER BY p90_min DESC NULLS LAST;
