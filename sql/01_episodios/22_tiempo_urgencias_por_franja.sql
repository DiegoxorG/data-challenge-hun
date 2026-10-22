-- Tiempo en urgencias según día y hora de llegada, por destino (insumo del heatmap). Agregado.
-- @include _episodios.sql
SELECT EXTRACT(ISODOW FROM llegada)::int AS dow,   -- 1 = lunes
       EXTRACT(HOUR   FROM llegada)::int AS hora,
       destino,
       COUNT(*) AS n,
       PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY min_urg) AS p50_min_urg,
       PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY min_urg) AS p90_min_urg
FROM epu
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;
