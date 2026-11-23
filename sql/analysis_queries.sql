-- Analysis queries on the star schema (SQLite: data/weather.db).
-- Grain of fact_weather_hourly: one row per city, per hour, per source.
-- Run: python run_sql.py


-- Query 1. Do we have data for every city and source, and which hours does it cover? (join)
SELECT c.city_name,
       f.source,
       COUNT(*)                 AS hourly_rows,
       MIN(f.observed_at_local) AS first_hour_local,
       MAX(f.observed_at_local) AS last_hour_local
FROM fact_weather_hourly AS f
JOIN dim_city AS c ON c.city_id = f.city_id
GROUP BY c.city_name, f.source
ORDER BY c.city_name, f.source;


-- Query 2. How cold was each city yesterday (UK calendar day), on average? (2 joins)
-- Uses dim_date, so the day boundary is always the London date, in winter and summer.
SELECT c.city_name,
       ROUND(AVG(f.temperature_c), 1) AS avg_temperature_c,
       ROUND(MIN(f.temperature_c), 1) AS min_temperature_c,
       ROUND(MAX(f.temperature_c), 1) AS max_temperature_c,
       COUNT(*)                       AS hours_covered
FROM fact_weather_hourly AS f
JOIN dim_city AS c ON c.city_id = f.city_id
JOIN dim_date AS d ON d.date_id = f.date_id
WHERE d.full_date = date('now', '-1 day')
GROUP BY c.city_name
ORDER BY avg_temperature_c;


-- Query 3. When and where was it windiest? The 5 windiest hours across all cities. (join)
SELECT c.city_name,
       f.observed_at_local,
       f.wind_speed_kmh,
       f.beaufort_scale,
       f.outdoor_work_risk
FROM fact_weather_hourly AS f
JOIN dim_city AS c ON c.city_id = f.city_id
ORDER BY f.wind_speed_kmh DESC, c.city_name, f.observed_at_utc
LIMIT 5;


-- Query 4. Data check: is the grain (city, hour, source) really unique after repeated runs?
-- Expect total_rows = distinct_keys.
SELECT COUNT(*) AS total_rows,
       COUNT(DISTINCT f.city_id || '|' || f.observed_at_utc || '|' || f.source) AS distinct_keys
FROM fact_weather_hourly AS f;


-- Query 5 (new). Is it windier at weekends than on weekdays, by city? (2 joins)
SELECT c.city_name,
       CASE d.is_weekend WHEN 1 THEN 'weekend' ELSE 'weekday' END AS day_type,
       ROUND(AVG(f.wind_speed_kmh), 1) AS avg_wind_kmh,
       COUNT(*)                        AS hours
FROM fact_weather_hourly AS f
JOIN dim_city AS c ON c.city_id = f.city_id
JOIN dim_date AS d ON d.date_id = f.date_id
GROUP BY c.city_name, day_type
ORDER BY c.city_name, day_type;


-- Query 6 (new). How many hours of each outdoor-work risk level per city, and in which country? (join)
SELECT c.country,
       c.city_name,
       SUM(f.outdoor_work_risk = 'high')   AS high_hours,
       SUM(f.outdoor_work_risk = 'medium') AS medium_hours,
       SUM(f.outdoor_work_risk = 'low')    AS low_hours
FROM fact_weather_hourly AS f
JOIN dim_city AS c ON c.city_id = f.city_id
GROUP BY c.country, c.city_name
ORDER BY high_hours DESC, medium_hours DESC;