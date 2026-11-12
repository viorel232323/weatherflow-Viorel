-- Week 1 queries on weather.db (SQLite), table weather_hourly.
-- Grain: one row per city per hour. observed_at is Europe/London local time, text 'YYYY-MM-DDTHH:MM'.
--
-- Run all of them from the repo root, with the virtual environment active:
--     python -m sqlite3 weather.db < sql/week1_queries.sql      (Mac/Linux shells, Git Bash)
--     Get-Content sql\week1_queries.sql | python -m sqlite3 weather.db   (Windows PowerShell)
-- or open weather.db in DataGrip / DB Browser for SQLite and run them one by one.


-- Query 1. Business question: do we have data for every city, and which hours does it cover?
-- Expect 5 rows. After one run on one day each city has 48 hours (yesterday 00:00 to today 23:00).
SELECT city,
       COUNT(*)         AS hourly_rows,
       MIN(observed_at) AS first_hour,
       MAX(observed_at) AS last_hour
FROM weather_hourly
GROUP BY city
ORDER BY city;


-- Query 2. Business question: how cold was each city yesterday, on average?
-- Planners use this to compare cities. hours_covered should be 24; fewer means a gap in the data.
-- date('now', '-1 day') uses UTC. In winter (GMT) London local time equals UTC, so this is exact;
-- during British Summer Time the day boundary is one hour off.
SELECT city,
       ROUND(AVG(temperature_c), 1) AS avg_temperature_c,
       ROUND(MIN(temperature_c), 1) AS min_temperature_c,
       ROUND(MAX(temperature_c), 1) AS max_temperature_c,
       COUNT(*)                     AS hours_covered
FROM weather_hourly
WHERE date(observed_at) = date('now', '-1 day')
GROUP BY city
ORDER BY avg_temperature_c;


-- Query 3. Business question: when and where was it windiest? Strong wind is a risk for outdoor work
-- (stages, scaffolding, marquees). The 5 windiest hours across all cities, strongest first.
SELECT city,
       observed_at,
       wind_speed_kmh,
       weather_code
FROM weather_hourly
ORDER BY wind_speed_kmh DESC, city, observed_at
LIMIT 5;


-- Query 4 (extra). Data check: is (city, observed_at) really unique after repeated runs?
-- Expect total_rows = distinct_keys. If they differ, the load is creating duplicates.
SELECT COUNT(*)                                   AS total_rows,
       COUNT(DISTINCT city || '|' || observed_at) AS distinct_keys
FROM weather_hourly;
