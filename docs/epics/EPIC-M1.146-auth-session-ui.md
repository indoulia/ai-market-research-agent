# EPIC-M1.146 — Authentication & Session UI

**Track:** UI
**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P0

## Objective
Provide a minimal, professional authentication/session experience for Flutter mobile and web without consuming valuable screen real estate.

## Scope
- Sign-in/session restoration flow using M1.145.
- Loading/authenticated/expired-session states.
- Logout/account action.
- Unauthorized/error messaging that is concise and actionable.
- Web deep-link return-to-original-screen after authentication.
- Mobile-safe input and keyboard handling.

## UX Rules
- No oversized marketing/login artwork unless required by product direction.
- Clear typography, compact form, strong primary action.
- Password/credential fields use platform-appropriate secure input.
- Session expiry should preserve intended navigation when possible.

## Acceptance Criteria
- Mobile and web share the same domain flow with adaptive layout.
- Expired sessions do not leave the user on a broken screen.
- Deep links return to the intended page after login.
- Accessibility and keyboard navigation pass.

## Parallelization
UI team against M1.145 mock contract.

## Dependencies
M1.133, M1.134, M1.145.
