-- Patrones de texto que mencionan triaje en measurement_source_value_extended
-- ⚠️ SENSIBLE: devuelve TEXTO LIBRE real (aunque agregado), que puede traer datos de un paciente.
-- El resultado no se comparte con nadie ni con ninguna IA; resumen_seguro.py solo dice si hay
-- coincidencias. Si hay que describirlo, se describe la FORMA con un valor inventado.
SELECT LEFT(measurement_source_value_extended, 80) AS texto, COUNT(*) AS n
FROM measurement
WHERE measurement_source_value_extended ILIKE ANY (ARRAY['%triag%','%triaj%','%clasif%'])
GROUP BY 1
ORDER BY n DESC
LIMIT 50;
