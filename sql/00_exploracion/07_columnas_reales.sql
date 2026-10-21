-- Esquema real de la BD: qué tablas y columnas existen y de qué tipo.
-- Solo metadatos (nombres y tipos), ningún dato de pacientes.
SELECT table_name, ordinal_position, column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'uninorte_omop'
ORDER BY table_name, ordinal_position;