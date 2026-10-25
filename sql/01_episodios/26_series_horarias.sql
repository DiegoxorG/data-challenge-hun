-- Series de tiempo HORARIAS para el pronóstico (agregado: una fila por hora, sin pacientes).
-- Rejilla completa: las horas sin eventos salen con 0 (la 21 solo trae las horas con llegadas).
--   llegadas                  episodios que empiezan en urgencias, por hora de llegada (como la 21)
--   llegadas_hospitalizan     de esas, las que terminan en cama
--   llegadas_contacto_breve   de esas, las de alta con menos de 15 min en urgencias (¿registro/remisión?)
--   ingresos_cama             hospitalizaciones que empiezan en la hora (vengan o no de urgencias)
--   ingresos_desde_urgencias  de esas, las de episodios que empezaron en urgencias
--   altas_cama                hospitalizaciones que terminan en la hora
--   censo_urgencias / censo_hospitalizacion  como la 25: urgencias cortado al ingreso a cama,
--                             sin urgencias > 7 días ni hospitalizaciones > 90 días
-- Va desde la primera hasta la última hora con llegadas (el censo se acumula desde antes).
-- @include _episodios.sql
, epu_aj AS (
  SELECT llegada, destino, min_urg, LEAST(fin_urg, COALESCE(ini_hosp, fin_urg)) AS fin_urg_aj
  FROM epu
), ev AS (
  SELECT date_trunc('hour', llegada) AS h, 1 AS llegadas,
         (destino = 'hospitalizado')::int AS llegadas_hospitalizan,
         (destino = 'alta' AND min_urg < 15)::int AS llegadas_contacto_breve,
         0 AS ingresos_cama, 0 AS ingresos_desde_urgencias, 0 AS altas_cama, 0 AS d_urg, 0 AS d_hosp
  FROM epu
  UNION ALL
  SELECT date_trunc('hour', llegada), 0, 0, 0, 0, 0, 0, 1, 0
  FROM epu_aj WHERE fin_urg_aj - llegada <= interval '7 days'
  UNION ALL
  SELECT date_trunc('hour', fin_urg_aj), 0, 0, 0, 0, 0, 0, -1, 0
  FROM epu_aj WHERE fin_urg_aj - llegada <= interval '7 days'
  UNION ALL
  SELECT date_trunc('hour', ini_hosp), 0, 0, 0, 1, (primer_cid IN (9203, 3045729))::int, 0, 0,
         (fin_hosp - ini_hosp <= interval '90 days')::int
  FROM ep WHERE ini_hosp IS NOT NULL
  UNION ALL
  SELECT date_trunc('hour', fin_hosp), 0, 0, 0, 0, 0, 1, 0,
         -((fin_hosp - ini_hosp <= interval '90 days')::int)
  FROM ep WHERE ini_hosp IS NOT NULL
), ph AS (
  SELECT h, SUM(llegadas) AS llegadas, SUM(llegadas_hospitalizan) AS llegadas_hospitalizan,
         SUM(llegadas_contacto_breve) AS llegadas_contacto_breve, SUM(ingresos_cama) AS ingresos_cama,
         SUM(ingresos_desde_urgencias) AS ingresos_desde_urgencias, SUM(altas_cama) AS altas_cama,
         SUM(d_urg) AS d_urg, SUM(d_hosp) AS d_hosp
  FROM ev GROUP BY h
), rejilla AS (
  SELECT generate_series(MIN(h), MAX(h), interval '1 hour') AS h FROM ph
), acumulado AS (
  SELECT r.h,
         COALESCE(p.llegadas, 0)                 AS llegadas,
         COALESCE(p.llegadas_hospitalizan, 0)    AS llegadas_hospitalizan,
         COALESCE(p.llegadas_contacto_breve, 0)  AS llegadas_contacto_breve,
         COALESCE(p.ingresos_cama, 0)            AS ingresos_cama,
         COALESCE(p.ingresos_desde_urgencias, 0) AS ingresos_desde_urgencias,
         COALESCE(p.altas_cama, 0)               AS altas_cama,
         SUM(COALESCE(p.d_urg, 0))  OVER (ORDER BY r.h) AS censo_urgencias,
         SUM(COALESCE(p.d_hosp, 0)) OVER (ORDER BY r.h) AS censo_hospitalizacion
  FROM rejilla r LEFT JOIN ph p ON p.h = r.h
)
SELECT h AS hora, llegadas, llegadas_hospitalizan, llegadas_contacto_breve, ingresos_cama,
       ingresos_desde_urgencias, altas_cama, censo_urgencias, censo_hospitalizacion
FROM acumulado
WHERE h BETWEEN (SELECT MIN(h) FROM ph WHERE llegadas > 0) AND (SELECT MAX(h) FROM ph WHERE llegadas > 0)
ORDER BY 1;
