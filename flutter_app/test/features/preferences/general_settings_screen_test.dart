import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mra_app/design_system/theme/mra_theme.dart';
import 'package:mra_app/features/preferences/general_settings_screen.dart';
import 'package:mra_app/features/preferences/preferences.dart';
import 'package:mra_app/features/preferences/preferences_repository.dart';

class _NeverResolvingRepository extends PreferencesRepository {
  // A Completer that's never completed, rather than Future.delayed, so no
  // real Timer is left pending when the test ends.
  final Completer<Preferences> _completer = Completer<Preferences>();

  @override
  Future<Preferences> fetch() => _completer.future;

  @override
  Future<Preferences> update(Preferences preferences) async => preferences;
}

class _FakePreferencesRepository extends PreferencesRepository {
  Preferences current;
  _FakePreferencesRepository(this.current);

  @override
  Future<Preferences> fetch() async => current;

  @override
  Future<Preferences> update(Preferences preferences) async {
    current = preferences;
    return preferences;
  }
}

class _FailOnceRepository extends PreferencesRepository {
  bool _failed = false;

  @override
  Future<Preferences> fetch() async {
    if (!_failed) {
      _failed = true;
      throw Exception('boom');
    }
    return Preferences.empty;
  }

  @override
  Future<Preferences> update(Preferences preferences) async => preferences;
}

Widget _wrapWithGallery(Widget child) {
  final router = GoRouter(
    routes: [
      GoRoute(path: '/settings', builder: (context, state) => child),
      GoRoute(
        path: '/dev/gallery',
        builder: (context, state) =>
            const Scaffold(body: Text('gallery placeholder')),
      ),
    ],
    initialLocation: '/settings',
  );
  return MaterialApp.router(theme: MraTheme.light(), routerConfig: router);
}

void main() {
  testWidgets(
    'About and the gallery link render even while preferences are still loading',
    (tester) async {
      await tester.pumpWidget(
        _wrapWithGallery(
          Scaffold(
            body: GeneralSettingsScreen(
              repository: _NeverResolvingRepository(),
            ),
          ),
        ),
      );
      await tester.pump();

      expect(find.text('Design system gallery (QA)'), findsOneWidget);
      expect(find.text('About'), findsOneWidget);
      // Appearance controls depend on the fetch and are not shown yet.
      expect(find.text('Appearance'), findsNothing);
    },
  );

  testWidgets(
    'a fetch failure renders the shared MraStateView.error, not a bespoke '
    'layout, and Retry recovers',
    (tester) async {
      await tester.pumpWidget(
        _wrapWithGallery(
          Scaffold(
            body: GeneralSettingsScreen(repository: _FailOnceRepository()),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(
        find.text('Appearance & refresh preferences unavailable'),
        findsOneWidget,
      );
      expect(find.byType(FilledButton), findsOneWidget);
      expect(find.text('Retry'), findsOneWidget);

      await tester.tap(find.text('Retry'));
      await tester.pumpAndSettle();

      expect(find.text('Appearance'), findsOneWidget);
    },
  );

  testWidgets('changing the theme mode saves via the repository', (
    tester,
  ) async {
    final repo = _FakePreferencesRepository(Preferences.empty);
    await tester.pumpWidget(
      _wrapWithGallery(Scaffold(body: GeneralSettingsScreen(repository: repo))),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Dark'));
    await tester.pumpAndSettle();

    expect(repo.current.displayPreferences.themeMode, AppThemeMode.dark);
  });

  testWidgets('tapping the gallery link navigates there', (tester) async {
    final repo = _FakePreferencesRepository(Preferences.empty);
    await tester.pumpWidget(
      _wrapWithGallery(Scaffold(body: GeneralSettingsScreen(repository: repo))),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Design system gallery (QA)'));
    await tester.pumpAndSettle();

    expect(find.text('gallery placeholder'), findsOneWidget);
  });
}
