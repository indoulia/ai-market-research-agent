# EPIC-M1.142 — Feedback, Preferences & Settings UI

**Track:** UI
**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P0

## Objective
Provide lightweight user controls for horizons, discovery scope, notifications, display preferences and manual recommendation feedback without cluttering the main experience.

## Screens
### Quick Preferences
- Default horizon: 1/2/3/5/7 trading days.
- Market/sector/industry/size filters.
- Watchlist.
- Notification toggles.

### Recommendation Feedback
- One-tap useful/not useful.
- Optional structured reason.
- Optional comment.
- Show acknowledgement that feedback is used for learning/analysis, not instant model changes.

### Settings
- Appearance/theme.
- Data refresh display preference.
- Notification preferences.
- About/version/data-provider transparency.

## UX Rules
- Preferences should be compact forms, not long settings pages.
- Use segmented controls, chips, switches and grouped cards.
- Feedback should take one or two interactions.
- Never use modal dialogs for routine feedback.
- Preserve unsaved form state safely and provide clear save status.

## Acceptance Criteria
- Default short-term horizon is configurable and starts at 1–7 days.
- User preferences persist through M1.141.
- Feedback references the exact recommendation version visible to the user.
- No UI promises that feedback immediately changes the model.
- Settings are responsive and keyboard/touch accessible.

## Parallelization
UI implementation against M1.141 fixture/OpenAPI data.

## Dependencies
M1.133, M1.134, M1.141.
