-- Cuántos segmentos tiene cada visita (distribución)
SELECT n_segmentos, COUNT(*) AS visitas
FROM (SELECT visit_occurrence_id, COUNT(*) AS n_segmentos
      FROM visit_detail GROUP BY 1) t
GROUP BY 1
ORDER BY 1;
