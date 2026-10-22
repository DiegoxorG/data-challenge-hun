-- Diagnóstico: ¿por qué la ocupación calculada supera tanto la capacidad?
-- Una sola fila de indicadores agregados.
-- @include _episodios.sql
, ep_ord AS (
  SELECT ep.*,
         MAX(fin_urg) OVER (PARTITION BY person_id ORDER BY ini
                            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS fin_urg_previo
  FROM ep
)
SELECT
  -- H1: ¿la atención de urgencias sigue abierta después de empezar la hospitalización?
  (SELECT AVG((fin_urg > ini_hosp)::int) FROM epu WHERE destino = 'hospitalizado')
      AS p_urg_sigue_tras_ingreso,
  (SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (fin_urg - ini_hosp)) / 60.0)
     FROM epu WHERE destino = 'hospitalizado' AND fin_urg > ini_hosp)
      AS p50_min_urg_tras_ingreso,
  (SELECT AVG((fin_urg >= fin_hosp)::int) FROM epu WHERE destino = 'hospitalizado')
      AS p_urg_cubre_toda_hosp,
  -- H2: ¿unos pocos episodios eternos se comen la ocupación?
  (SELECT AVG((min_urg > 4320)::int)  FROM epu) AS p_epis_urg_mas_3d,
  (SELECT AVG((min_urg > 10080)::int) FROM epu) AS p_epis_urg_mas_7d,
  (SELECT AVG((min_urg > 43200)::int) FROM epu) AS p_epis_urg_mas_30d,
  (SELECT SUM(min_urg) FILTER (WHERE min_urg > 1440)  / NULLIF(SUM(min_urg), 0) FROM epu) AS p_horas_urg_de_epis_mas_24h,
  (SELECT SUM(min_urg) FILTER (WHERE min_urg > 10080) / NULLIF(SUM(min_urg), 0) FROM epu) AS p_horas_urg_de_epis_mas_7d,
  (SELECT AVG((EXTRACT(EPOCH FROM (fin_hosp - ini_hosp)) / 60.0 > 43200)::int)
     FROM ep WHERE ini_hosp IS NOT NULL) AS p_hosp_mas_30d,
  -- Episodios "alta" muy cortos: ¿estancias o solo registros?
  (SELECT AVG((min_urg < 15)::int) FROM epu WHERE destino = 'alta') AS p_alta_menos_15min,
  -- Hueco entre fin de urgencias y una hospitalización que llega dentro de 48 h (¿espera de cama no registrada?)
  (SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (ini - fin_urg_previo)) / 60.0)
     FROM ep_ord WHERE primer_cid = 9201 AND ini - fin_urg_previo <= interval '48 hours')
      AS p50_min_hueco_urg_hosp_48h,
  (SELECT AVG((ini - fin_urg_previo <= interval '6 hours')::int)
     FROM ep_ord WHERE primer_cid = 9201 AND ini - fin_urg_previo <= interval '48 hours')
      AS p_hueco_menos_6h;