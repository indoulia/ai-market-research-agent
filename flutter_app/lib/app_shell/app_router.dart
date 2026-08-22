import 'package:go_router/go_router.dart';

import '../core/auth/auth_controller.dart';
import '../features/auth/sign_in_screen.dart';
import '../features/auth/splash_screen.dart';
import '../features/dashboard/dashboard_screen.dart';
import '../features/detail/recommendation_detail_screen.dart';
import '../features/discover/discover_screen.dart';
import '../features/history/history_screen.dart';
import '../features/learning/learning_screen.dart';
import '../features/market/market_screen.dart';
import '../features/opportunities/opportunity_explorer_screen.dart';
import '../features/preferences/preferences_settings_screen.dart';
import '../features/tracking/tracking_screen.dart';
import '../gallery/gallery_screen.dart';
import 'app_destination.dart';
import 'app_shell_scaffold.dart';

/// EPIC-M1.134 — route table. One [StatefulShellRoute] branch per primary
/// destination so each keeps independent navigation/scroll state when the
/// user switches tabs (mobile bottom nav or web/desktop nav rail).
///
/// [buildAppRouter] returns a fresh [GoRouter] each call — tests use it to
/// avoid sharing navigation state across test cases; [appRouter] is the one
/// long-lived instance the running app uses.
final GoRouter appRouter = buildAppRouter();

/// EPIC-M1.146 — [authController] is optional and opt-in: passing none (as
/// every pre-existing test and call site does) reproduces the exact
/// pre-M1.146 router with no `/sign-in`/`/splash` routes and no redirect,
/// so this epic adds auth gating without changing behavior for anything
/// that doesn't ask for it. Only [main.dart]'s real app passes a real,
/// restoring [AuthController].
GoRouter buildAppRouter({AuthController? authController}) => GoRouter(
  initialLocation: authController != null ? '/splash' : '/home',
  refreshListenable: authController,
  redirect: authController == null
      ? null
      : (context, state) {
          final status = authController.status;
          final loc = state.matchedLocation;
          if (status == AuthStatus.restoring) {
            return loc == '/splash' ? null : '/splash';
          }
          final needsSignIn =
              status == AuthStatus.unauthenticated ||
              status == AuthStatus.sessionExpired;
          if (needsSignIn) {
            if (loc == '/sign-in') return null;
            return '/sign-in?from=${Uri.encodeComponent(loc)}';
          }
          if (loc == '/splash' || loc == '/sign-in') {
            final from = state.uri.queryParameters['from'];
            return (from != null && from.isNotEmpty) ? from : '/home';
          }
          return null;
        },
  routes: [
    if (authController != null) ...[
      GoRoute(
        path: '/splash',
        builder: (context, state) => const SplashScreen(),
      ),
      GoRoute(
        path: '/sign-in',
        builder: (context, state) => SignInScreen(
          controller: authController,
          redirectTo: state.uri.queryParameters['from'],
        ),
      ),
    ],
    StatefulShellRoute.indexedStack(
      builder: (context, state, navigationShell) =>
          AppShellScaffold(navigationShell: navigationShell),
      branches: [
        StatefulShellBranch(
          routes: [
            GoRoute(
              path: kAppDestinations[0].path,
              builder: (context, state) => const DashboardScreen(),
              routes: [
                GoRoute(
                  path: 'recommendation/:id',
                  builder: (context, state) => RecommendationDetailScreen(
                    recommendationId: int.parse(state.pathParameters['id']!),
                  ),
                ),
              ],
            ),
          ],
        ),
        StatefulShellBranch(
          routes: [
            GoRoute(
              path: kAppDestinations[1].path,
              builder: (context, state) => const DiscoverScreen(),
              routes: [
                GoRoute(
                  path: 'recommendation/:id',
                  builder: (context, state) => RecommendationDetailScreen(
                    recommendationId: int.parse(state.pathParameters['id']!),
                  ),
                ),
              ],
            ),
          ],
        ),
        StatefulShellBranch(
          routes: [
            GoRoute(
              path: kAppDestinations[2].path,
              builder: (context, state) => const TrackingScreen(),
              routes: [
                GoRoute(
                  path: 'recommendation/:id',
                  builder: (context, state) => RecommendationDetailScreen(
                    recommendationId: int.parse(state.pathParameters['id']!),
                  ),
                ),
                GoRoute(
                  path: 'learning',
                  builder: (context, state) => const LearningScreen(),
                ),
              ],
            ),
          ],
        ),
        StatefulShellBranch(
          routes: [
            GoRoute(
              path: kAppDestinations[3].path,
              builder: (context, state) => const MarketScreen(),
              routes: [
                GoRoute(
                  path: 'recommendation/:id',
                  builder: (context, state) => RecommendationDetailScreen(
                    recommendationId: int.parse(state.pathParameters['id']!),
                  ),
                ),
              ],
            ),
          ],
        ),
        StatefulShellBranch(
          routes: [
            GoRoute(
              path: kAppDestinations[4].path,
              builder: (context, state) => const OpportunityExplorerScreen(),
              routes: [
                GoRoute(
                  path: 'recommendation/:id',
                  builder: (context, state) => RecommendationDetailScreen(
                    recommendationId: int.parse(state.pathParameters['id']!),
                  ),
                ),
              ],
            ),
          ],
        ),
        StatefulShellBranch(
          routes: [
            GoRoute(
              path: kAppDestinations[5].path,
              builder: (context, state) => const HistoryScreen(),
              routes: [
                GoRoute(
                  path: 'recommendation/:id',
                  builder: (context, state) => RecommendationDetailScreen(
                    recommendationId: int.parse(state.pathParameters['id']!),
                  ),
                ),
              ],
            ),
          ],
        ),
        StatefulShellBranch(
          routes: [
            GoRoute(
              path: kAppDestinations[6].path,
              builder: (context, state) =>
                  PreferencesSettingsScreen(authController: authController),
            ),
          ],
        ),
      ],
    ),
    GoRoute(
      path: '/dev/gallery',
      builder: (context, state) => const GalleryScreen(),
    ),
  ],
);
