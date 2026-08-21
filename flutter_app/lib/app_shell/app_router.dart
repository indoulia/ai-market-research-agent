import 'package:go_router/go_router.dart';

import '../features/dashboard/dashboard_screen.dart';
import '../features/detail/recommendation_detail_screen.dart';
import '../features/discover/discover_screen.dart';
import '../features/market/market_screen.dart';
import '../features/preferences/preferences_settings_screen.dart';
import '../gallery/gallery_screen.dart';
import 'app_destination.dart';
import 'app_shell_scaffold.dart';
import 'placeholder_screen.dart';

/// EPIC-M1.134 — route table. One [StatefulShellRoute] branch per primary
/// destination so each keeps independent navigation/scroll state when the
/// user switches tabs (mobile bottom nav or web/desktop nav rail).
///
/// [buildAppRouter] returns a fresh [GoRouter] each call — tests use it to
/// avoid sharing navigation state across test cases; [appRouter] is the one
/// long-lived instance the running app uses.
final GoRouter appRouter = buildAppRouter();

GoRouter buildAppRouter() => GoRouter(
  initialLocation: '/home',
  routes: [
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
              builder: (context, state) => DestinationPlaceholderScreen(
                destination: kAppDestinations[2],
              ),
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
              builder: (context, state) => DestinationPlaceholderScreen(
                destination: kAppDestinations[4],
              ),
            ),
          ],
        ),
        StatefulShellBranch(
          routes: [
            GoRoute(
              path: kAppDestinations[5].path,
              builder: (context, state) => const PreferencesSettingsScreen(),
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
