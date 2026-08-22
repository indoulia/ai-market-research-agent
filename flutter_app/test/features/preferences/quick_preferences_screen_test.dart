import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mra_app/design_system/theme/mra_theme.dart';
import 'package:mra_app/features/preferences/preferences.dart';
import 'package:mra_app/features/preferences/preferences_repository.dart';
import 'package:mra_app/features/preferences/quick_preferences_screen.dart';

class _FakePreferencesRepository extends PreferencesRepository {
  Preferences current;
  final bool failUpdate;

  _FakePreferencesRepository({required this.current, this.failUpdate = false});

  @override
  Future<Preferences> fetch() async => current;

  @override
  Future<Preferences> update(Preferences preferences) async {
    if (failUpdate) throw Exception('boom');
    current = preferences;
    return preferences;
  }
}

Widget _wrap(Widget child) {
  return MaterialApp(
    theme: MraTheme.light(),
    home: Scaffold(body: child),
  );
}

void main() {
  testWidgets('loads and renders the current preferences', (tester) async {
    final repo = _FakePreferencesRepository(
      current: Preferences.empty.copyWith(defaultHorizon: 5),
    );
    await tester.pumpWidget(_wrap(QuickPreferencesScreen(repository: repo)));
    await tester.pumpAndSettle();

    expect(find.text('Quick Preferences'), findsOneWidget);
    expect(find.text('Watchlist'), findsOneWidget);
  });

  testWidgets('adding a watchlist symbol saves and shows "Saved"', (
    tester,
  ) async {
    final repo = _FakePreferencesRepository(current: Preferences.empty);
    await tester.pumpWidget(_wrap(QuickPreferencesScreen(repository: repo)));
    await tester.pumpAndSettle();

    // Watchlist's TextField is the first of two (Watchlist, then Sectors).
    await tester.enterText(find.byType(TextField).first, 'TATASTEEL');
    await tester.tap(find.byIcon(Icons.add).first);
    await tester.pumpAndSettle();

    expect(find.text('TATASTEEL'), findsOneWidget);
    expect(find.text('Saved'), findsOneWidget);
    expect(repo.current.watchlist, contains('TATASTEEL'));
  });

  testWidgets(
    'the save status label is a live region (EPIC-M3.13: the only cue an '
    'autosave succeeded/failed must be announced, not just shown visually)',
    (tester) async {
      final handle = tester.ensureSemantics();
      final repo = _FakePreferencesRepository(current: Preferences.empty);
      await tester.pumpWidget(_wrap(QuickPreferencesScreen(repository: repo)));
      await tester.pumpAndSettle();

      await tester.tap(find.text('5D'));
      await tester.pumpAndSettle();

      final semantics = tester.getSemantics(find.text('Saved'));
      expect(semantics.flagsCollection.isLiveRegion, isTrue);
      handle.dispose();
    },
  );

  testWidgets('a failed save shows "Save failed"', (tester) async {
    final repo = _FakePreferencesRepository(
      current: Preferences.empty,
      failUpdate: true,
    );
    await tester.pumpWidget(_wrap(QuickPreferencesScreen(repository: repo)));
    await tester.pumpAndSettle();

    await tester.tap(find.text('5D'));
    await tester.pumpAndSettle();

    expect(find.text('Save failed'), findsOneWidget);
  });

  testWidgets('shows an error state when the initial fetch fails', (
    tester,
  ) async {
    final repo = _FailingFetchRepository();
    await tester.pumpWidget(_wrap(QuickPreferencesScreen(repository: repo)));
    await tester.pumpAndSettle();

    expect(find.text('Something went wrong'), findsOneWidget);
  });
}

class _FailingFetchRepository extends PreferencesRepository {
  @override
  Future<Preferences> fetch() async => throw Exception('boom');

  @override
  Future<Preferences> update(Preferences preferences) async => preferences;
}
