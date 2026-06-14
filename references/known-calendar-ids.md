# Known-Good Calendar IDs

Verified working calendar IDs for this environment (as of 2026-06-13):

| Calendar | ID | Access | Notes |
|---|---|---|---|
| Personal | `google-workspace-user` | Read (direct API + MCP) | The working personal calendar |
| Family | `family08350553536598846140@group.v.calendar.google.com` | 404 (inaccessible) | Listed by MCP list_calendars but returns 404 on query |
| Primary (MCP) | `mx.indigo.karasu@gmail.com` | 404 on direct API | Shown by MCP list_calendars but not queryable via direct fallback |

## Recommendation

Set `config.json` `primary_calendar_ids` to explicit working IDs:

```json
"primary_calendar_ids": ["google-workspace-user"]
```

Do not use `["primary"]` as a calendar ID in `primary_calendar_ids` — it's ambiguous and may resolve differently between MCP and direct fallback paths.

Also add the `last_evening_brief` field to config (only `last_morning_brief` exists in the default template):

```json
"last_evening_brief": null
```

## Calendar ID Detection

To find working calendar IDs:
1. Call `mcp_google_workspace_list_calendars` to enumerate all visible calendars
2. For each calendar ID, attempt a test query via direct Python fallback
3. Log which IDs return events vs 404
4. Update `config.json` with only the working IDs
