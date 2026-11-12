# Week 1 Deliverables Checklist

**Due: Wednesday 11 November 2026, 18:00 UK** · Reviewed in Live Session 2, Thursday 12 November

Status as of Thursday 12 November 2026. Items marked ⏳ still need action from me.

## Repository

- [ ] ⏳ **D1.1** Repo `weatherflow-viorel` shared with programme lead (repo built and committed locally; still to push to GitHub and add the programme lead as a collaborator)
- [x] `README.md` with goal, setup steps and how to run
- [x] `.gitignore` excludes `.venv/`, `data/`, `.env`, `*.db` (checked with `git check-ignore -v`)
- [x] `requirements.txt` installs cleanly (checked in a fresh clone with a new `.venv`; `pip check` clean)
- [x] At least 8 commits with meaningful messages (13 commits), though made in one sitting rather than spread across the week

## Understanding the reference

- [x] **D1.2** `docs/reference_architecture.md` (Mermaid) and `docs/reference_architecture.png`, with E/T/L labels
- [x] `docs/reference_critique.md` with a 7-row component table, 5 problems with evidence, and an essential vs overkill view

## Extract

- [x] **D1.3** `extract.py` lands raw JSON for 5 cities in `data/raw/<YYYY-MM-DD>/`
- [x] Failures for one city do not stop the others (tested with latitude 999 and an unreachable host)

## Explore

- [x] **D1.4** `notebooks/01_explore.ipynb` runs top to bottom, includes 1 chart and 6 findings
- [x] `docs/data_dictionary.md` covers every column, units and grain

## ETL

- [x] **D1.5** `etl_v1.py` runs extract → transform → load in one command
- [x] Re-running gives the same row count (240 → 240, 240 distinct keys)
- [x] `sql/week1_queries.sql` with 3 commented queries (plus a duplicate check)

## Reflection and practice

- [ ] ⏳ **D1.6** `docs/reflections/week_1.md`: draft written, still to rewrite in my own words
- [ ] ⏳ Skills tracker updated
- [ ] ⏳ Attended Live Session 1 (Thu 5 Nov)
- [ ] ⏳ Weekly update posted (Tue 10 Nov, by 21:00)
- [ ] ⏳ Show-and-tell (3–5 min) ready for Live Session 2 (Thu 12 Nov, 20:00)
