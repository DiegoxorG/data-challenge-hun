-- Entrada de la herramienta Cuellos_botella: un segmento de visit_detail por fila, con
-- su paciente, el nombre del concepto y los atributos de la sección H.
--
-- @nivel_paciente
-- ES NIVEL PACIENTE. hun.extract se niega a correrlo (lo guardaría en un parquet).
-- Se usa así, y se lee directo a memoria sin escribir nada por paciente en disco:
--   python -m Cuellos_botella --config Cuellos_botella/config.yaml --entrada sql/02_cuellos_botella/entrada.sql
--
-- Mismos conceptos que _episodios.sql (9203 llegada, 3045729 atención, 9201 hospitalización).
-- A diferencia de _episodios.sql, NO filtra segmentos con fin < inicio ni sin fin: la sección
-- de calidad los cuenta y la herramienta los descarta igual que el SQL.
SELECT vo.person_id,
       vd.visit_detail_concept_id,
       vd.visit_detail_start_datetime,
       vd.visit_detail_end_datetime,
       c.concept_name,
       p.gender_concept_id,
       p.year_of_birth
FROM visit_detail vd
JOIN visit_occurrence vo ON vo.visit_occurrence_id = vd.visit_occurrence_id
LEFT JOIN person p       ON p.person_id = vo.person_id
LEFT JOIN concept c      ON c.concept_id = vd.visit_detail_concept_id
WHERE vd.visit_detail_concept_id IN (9203, 3045729, 9201)
