-- Serie de tiempo: llegadas a urgencias por hora (insumo del pronóstico). Agregado.
-- OJO: solo trae las horas CON llegadas; las horas sin llegadas no aparecen. Para series de
-- tiempo usa 26_series_horarias.sql, que trae la rejilla completa con ceros.
-- @include _episodios.sql
SELECT date_trunc('hour', llegada) AS hora,
       COUNT(*) AS llegadas,
       COUNT(*) FILTER (WHERE destino = 'hospitalizado') AS llegadas_que_se_hospitalizan
FROM epu
GROUP BY 1
ORDER BY 1;
