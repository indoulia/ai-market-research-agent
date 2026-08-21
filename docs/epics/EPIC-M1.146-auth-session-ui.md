# EPIC-M1.146 — Authentication & Session UI

**Track:** UI
**Status:** DONE
**Execution Status:** COMPLETE
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

## Completion Report

**Status:** DONE

### What was built
- `lib/core/auth/auth_session.dart` — `AuthSession` parsed from M1.145's real, merged `SessionResponse`/`UserContext` shape (`sessionToken`, `userId`, `issuedAt`, `expiresAt`), with an `isExpired` getter and JSON round-trip for local persistence.
- `lib/core/auth/auth_repository.dart` — thin repository over the real `POST /auth/session` (sign-in/refresh) and `POST /auth/logout` endpoints (confirmed against `api/schemas/auth.py` / `api/routers/auth.py` / `api/deps.py` on `main`, not guessed from the epic doc's prose).
- `lib/core/auth/auth_controller.dart` — a `ChangeNotifier`-based `AuthController` with `AuthStatus { restoring, authenticated, sessionExpired, unauthenticated }`. `restore()` reads a persisted session from `shared_preferences` at cold start and classifies it into one of the four states; `signIn()`/`signOut()` drive the rest. Session storage is a deliberately ordinary `SharedPreferencesAsync` string (not secure-storage) because M1.145's own completion report documents its backend auth as a self-asserted placeholder with no real credential verifier yet — bank-grade local storage would imply a security property the platform doesn't actually have.
- `lib/core/api_client.dart` — added a static `bearerToken` (attached as `Authorization: Bearer <token>` to every request from every repository, set from one place) and a static `onSessionExpired` hook: any response whose error envelope carries `MRA_SESSION_EXPIRED` now calls back into whichever `AuthController` is live, regardless of which repository/screen made the request. This is what makes a session that expires **mid-session** (not just at the next cold start) immediately flip global auth state and redirect to sign-in — directly satisfying the epic's "expired sessions do not leave the user on a broken screen" acceptance criterion, not just the cold-start case.
- `lib/features/auth/sign_in_screen.dart` — compact sign-in form: a single "User ID" field (no password field — there is no real credential to check yet, and adding one would be UX theater), a warning chip when arriving via an expired session, inline error text, keyboard `TextInputAction.done`/`onSubmitted` support.
- `lib/features/auth/splash_screen.dart` — shown only while `AuthStatus.restoring` (a real, momentary async state, not a placeholder).
- `lib/app_shell/app_router.dart` — `buildAppRouter` now takes an **optional** `AuthController? authController`. When omitted (every pre-existing call site and test), the router is byte-for-byte the pre-M1.146 router — no `/sign-in`/`/splash` routes, no redirect — so this epic adds nothing that could regress M1.133/M1.134's existing behavior. When supplied, `refreshListenable: authController` plus a `redirect` callback gates every route: `restoring` → `/splash`; `unauthenticated`/`sessionExpired` → `/sign-in?from=<original path>`; `authenticated` while on `/splash`/`/sign-in` → the preserved `from` path or `/home`. This is the actual mechanism behind the "web deep-link return-to-original-screen after authentication" AC — verified end-to-end in tests, not just asserted.
- `lib/main.dart` — the real app now constructs one real `AuthController`, calls `restore()` at startup, and builds its router with that controller. A test-only `authController` constructor seam on `MraApp` lets tests inject a pre-set controller instead of hitting real `shared_preferences`/network.
- `lib/features/preferences/general_settings_screen.dart` (+ `preferences_settings_screen.dart` threading it through) — added an "Account" section showing the signed-in user id and a "Sign out" action, calling `AuthController.signOut()`. Hidden entirely when no `AuthController` is supplied (QA gallery, all pre-existing tests) — the logout/account-action item from Scope.

### Real bugs found and fixed while integrating
- A plain `AuthController()` that is pre-set to `authenticated` and never has `restore()`/`signIn()`/`signOut()` called on it (the pattern used by every non-auth-focused test, e.g. `test/widget_test.dart`) originally still eagerly constructed a real `SharedPreferencesAsync()` in its constructor — which throws `Bad state: The SharedPreferencesAsyncPlatform instance must be set` in a test binding with no platform mock registered. Fixed by making `_prefs` lazy (only constructed on first actual use inside `restore()`/`signIn()`/`signOut()`), so a controller that's never asked to touch storage never needs a registered platform.
- `test/widget_test.dart`'s original assertion ("App boots into the Home destination") broke once the real app started gating on auth by default, since an unauthenticated app now lands on `/sign-in`, not `/home`. Fixed by giving `MraApp` a test seam to inject an already-`authenticated` controller — the correct fix (the test's intent — "does the shell render" — didn't change, only the app's real default behavior did).

### Honest gaps / known limitations
- `AuthRepository.refresh()` exists (mirrors M1.145's `POST /auth/session` refresh contract) but nothing calls it — there is no proactive "refresh before expiry" background timer. Sessions are re-validated on cold start (`restore()`) and reactively the moment any request returns `MRA_SESSION_EXPIRED` (see the `onSessionExpired` hook above); there is no additional periodic check while the app sits idle and connected.
- `/dev/gallery` is now behind the same auth gate as every other route when a real `AuthController` is wired in (i.e. in the running app, not in tests that omit `authController`). This is a real behavior change from M1.133's originally ungated gallery link — treated as correct rather than worked around, since gating "every route except sign-in/splash" is the simpler, more honest contract than special-casing one QA-only route to bypass auth.
- Accessibility beyond what Material's stock `TextField`/`FilledButton`/`Scaffold` provide out of the box was not added bespoke (no custom `Semantics` wrapping on the sign-in form) — these widgets already carry accessible semantics by default, and the form is simple enough (one field, one button) that no custom labeling was judged necessary.

### Testing
- `test/core/auth/auth_repository_test.dart` — `signIn`/`logout` request shape and response decoding, plus an error-envelope case, against a fake `http.Client` (matching `test/core/api_client_test.dart`'s existing pattern).
- `test/core/auth/auth_controller_test.dart` — `restore()` across no-session/valid-session/expired-session, `signIn()` success/failure, `signOut()` (including when the server-side logout call itself throws), listener notifications, and the mid-session `MRA_SESSION_EXPIRED` hook (including that `dispose()` correctly unregisters it so a disposed controller can never react to a stale hook). Uses `InMemorySharedPreferencesAsync` from `shared_preferences_platform_interface` (added as a dev dependency) rather than any hand-rolled fake.
- `test/features/auth/sign_in_screen_test.dart` — no password field present, error display on failed sign-in, the session-expired banner, and that submitting an empty user id is a no-op.
- `test/app_shell/app_router_auth_test.dart` — the full redirect matrix end-to-end through a real `GoRouter`: splash while restoring, unauthenticated → sign-in with the deep link preserved in `from`, the expired-session banner, authenticated bypassing sign-in straight to `/home`, a real sign-in flow navigating back to the originally-requested deep link, and sign-out (from the Settings screen) bouncing back to sign-in.
- Full existing suite (`flutter test`) re-run after every change in this epic: 99/99 passing, zero regressions to M1.133/M1.134/M1.136/M1.138/M1.140/M1.142/M1.143's tests.
- `flutter analyze`: no issues.
