-- Bloque común (no se corre solo): reconstruye EPISODIOS a partir de visit_detail.
-- Por qué: una visit_occurrence del HUN agrupa segmentos separados por días, así que
-- no sirve como episodio. Aquí unimos, por paciente, los segmentos de urgencias
-- (9203 llegada, 3045729 atención) y hospitalización (9201) que van seguidos o
-- solapados, y cortamos donde hay un hueco mayor a gap_min minutos.
--   ep  : todos los episodios (con o sin urgencias)
--   epu : episodios que EMPIEZAN en urgencias, con destino y tiempos en minutos
WITH params AS (
  SELECT 60 AS gap_min          -- hueco máximo para considerar "el mismo episodio"
),
seg AS (
  SELECT vo.person_id,
         vd.visit_detail_id,
         vd.visit_detail_concept_id     AS cid,
         vd.visit_detail_start_datetime AS ini,
         vd.visit_detail_end_datetime   AS fin
  FROM visit_detail vd
  JOIN visit_occurrence vo ON vo.visit_occurrence_id = vd.visit_occurrence_id
  WHERE vd.visit_detail_concept_id IN (9203, 3045729, 9201)
    AND vd.visit_detail_end_datetime >= vd.visit_detail_start_datetime
),
marcas AS (
  SELECT s.*,
         MAX(s.fin) OVER (PARTITION BY s.person_id ORDER BY s.ini, s.visit_detail_id
                          ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS fin_previo
  FROM seg s
),
islas AS (
  SELECT m.*,
         SUM(CASE WHEN m.fin_previo IS NULL
                    OR m.ini > m.fin_previo + make_interval(mins => p.gap_min)
                  THEN 1 ELSE 0 END)
           OVER (PARTITION BY m.person_id ORDER BY m.ini, m.visit_detail_id) AS isla
  FROM marcas m CROSS JOIN params p
),
ep AS (
  SELECT person_id, isla,
         MIN(ini) AS ini,
         MAX(fin) AS fin,
         (ARRAY_AGG(cid ORDER BY ini, visit_detail_id))[1]       AS primer_cid,
         MIN(ini) FILTER (WHERE cid IN (9203, 3045729))          AS llegada,
         MAX(fin) FILTER (WHERE cid IN (9203, 3045729))          AS fin_urg,
         MIN(ini) FILTER (WHERE cid = 9201)                      AS ini_hosp,
         MAX(fin) FILTER (WHERE cid = 9201)                      AS fin_hosp,
         COUNT(*)                                                AS n_seg
  FROM islas
  GROUP BY person_id, isla
),
epu AS (
  SELECT ep.*,
         CASE WHEN ini_hosp IS NOT NULL THEN 'hospitalizado' ELSE 'alta' END AS destino,
         EXTRACT(EPOCH FROM (fin_urg  - llegada))  / 60.0 AS min_urg,
         EXTRACT(EPOCH FROM (fin_hosp - ini_hosp)) / 60.0 AS min_hosp,
         EXTRACT(EPOCH FROM (ini_hosp - fin_urg))  / 60.0 AS min_hueco_urg_hosp
  FROM ep
  WHERE primer_cid IN (9203, 3045729)
)