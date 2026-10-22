-- Patrones de texto que mencionan triaje en measurement_source_value_extended
SELECT LEFT(measurement_source_value_extended, 80) AS texto, COUNT(*) AS n
FROM measurement
WHERE measurement_source_value_extended ILIKE ANY (ARRAY['%triag%','%triaj%','%clasif%'])
GROUP BY 1
ORDER BY n DESC
LIMIT 50;
