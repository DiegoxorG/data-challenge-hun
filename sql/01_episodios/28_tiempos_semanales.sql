-- Tiempo en urgencias y estancia en cama por SEMANA de llegada y destino (agregado).
-- Por semana y no por día para que cada percentil resuma a muchos pacientes: los grupos con
-- menos de 10 episodios se descartan (protocolo: grupos pequeños se tratan como sensibles).
--   p50/p90_h_urg            sin recorte (como la 20: incluye el tiempo en cama si urgencias
--                            siguió abierto después del ingreso)
--   p50/p90_h_urg_recortado  con urgencias cortado al ingreso a cama (como la 25)
--   p50_dias_cama            estancia en cama de los hospitalizados
-- Las últimas semanas subestiman las estancias largas (aún no terminaban al extraer).
-- @include _episodios.sql
SELECT date_trunc('week', llegada)::date AS semana, destino,
       COUNT(*) AS episodios,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY min_urg) / 60 AS p50_h_urg,
       PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY min_urg) / 60 AS p90_h_urg,
       PERCENTILE_CONT(0.5) WITHIN GROUP (
         ORDER BY EXTRACT(EPOCH FROM (LEAST(fin_urg, COALESCE(ini_hosp, fin_urg)) - llegada)) / 60) / 60
         AS p50_h_urg_recortado,
       PERCENTILE_CONT(0.9) WITHIN GROUP (
         ORDER BY EXTRACT(EPOCH FROM (LEAST(fin_urg, COALESCE(ini_hosp, fin_urg)) - llegada)) / 60) / 60
         AS p90_h_urg_recortado,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY min_hosp) / 1440 AS p50_dias_cama
FROM epu
GROUP BY 1, 2
HAVING COUNT(*) >= 10
ORDER BY 1, 2;
