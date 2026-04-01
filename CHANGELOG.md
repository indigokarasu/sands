# Changelog

All notable changes to ocas-sands will be documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html):
patch = bugfix or text, minor = new commands, major = new features.

---

## [1.0.0] — 2026-03-31

### Added
- `sands.query` — pull events for a natural-language time window
- `sands.create` — create events from natural language with conflict pre-check
- `sands.modify` — update existing events with post-modify conflict re-check
- `sands.conflicts` — analyze a time window with FIXED / FLEXIBLE / AMBIGUOUS classification
- `sands.travel` — insert travel time blocks via Google Places Distance Matrix API
- `sands.brief` — emit InsightProposal to Vesper intake (evening and morning modes)
- `sands.status` — skill health and configuration summary
- Work calendar busy overlay (titles suppressed, shown as "Busy (work)")
- Location-aware travel departure resolution (prior event → system location → user prompt)
- Preparation signal detection for morning briefs
- Journal output for every command run
