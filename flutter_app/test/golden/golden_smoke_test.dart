import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mra_app/core/auth/auth_controller.dart';
import 'package:mra_app/core/auth/auth_repository.dart';
import 'package:mra_app/core/auth/auth_session.dart';
import 'package:mra_app/design_system/design_system.dart';
import 'package:mra_app/features/auth/sign_in_screen.dart';

/// EPIC-M3.14 — golden tests for critical layouts. No prior EPIC (M1.144's
/// E2E suite, any per-screen widget test, or M3.13's
/// `accessibility_and_responsive_test.dart`) uses `matchesGoldenFile` --
/// every existing assertion is text/semantics/exception-based, so a purely
/// visual regression (spacing, alignment, color-token drift) could ship
/// undetected. These are deliberately scoped to a handful of the most
/// widely-reused, deterministic layouts (no charts/images/real fonts) to
/// keep them stable in `flutter test`'s software-rendered environment.
///
/// These goldens were generated on Windows; CI (`flutter-ci.yml`) runs the
/// identical pinned Flutter version on `ubuntu-latest`, and a first CI run
/// showed small (<=1.82%) pixel diffs on every one of the three goldens —
/// Skia's software rasterizer is not perfectly byte-identical across host
/// OSes even with no custom fonts declared (no `fonts:` section exists in
/// `pubspec.yaml`), evidently down to sub-pixel anti-aliasing/hinting
/// differences. A byte-exact `LocalFileComparator` would make these
/// permanently red in CI without any real regression. [_TolerantGoldenFileComparator]
/// tolerates that specific, observed class of cross-OS noise (a generous
/// multiple of the largest diff actually seen) while still failing on a
/// real visual regression, which changes far more than a few percent of
/// pixels.
class _TolerantGoldenFileComparator extends LocalFileComparator {
  _TolerantGoldenFileComparator(super.testFile);

  static const double _maxTolerableDiffPercent = 0.05;

  @override
  Future<bool> compare(Uint8List imageBytes, Uri golden) async {
    final result = await GoldenFileComparator.compareLists(
      imageBytes,
      await getGoldenBytes(golden),
    );
    if (result.passed || result.diffPercent <= _maxTolerableDiffPercent) {
      result.dispose();
      return true;
    }
    final error = await generateFailureOutput(result, golden, basedir);
    result.dispose();
    throw FlutterError(error);
  }
}

class _NeverSignsInAuthRepository extends AuthRepository {
  @override
  Future<AuthSession> signIn(String userId) =>
      Future.delayed(const Duration(days: 1), () => throw UnimplementedError());
}

Future<void> _setGoldenSurface(WidgetTester tester, Size size) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

void main() {
  setUpAll(() {
    goldenFileComparator = _TolerantGoldenFileComparator(
      Uri.file('${Directory.current.path}/test/golden/golden_smoke_test.dart'),
    );
  });

  testWidgets('recommendation card (populated) golden', (tester) async {
    await _setGoldenSurface(tester, const Size(400, 320));
    await tester.pumpWidget(
      MaterialApp(
        theme: MraTheme.light(),
        home: Scaffold(
          body: Padding(
            padding: const EdgeInsets.all(MraSpacing.md),
            child: RecommendationCard(
              data: RecommendationCardData(
                symbol: 'TATASTEEL',
                companyName: 'Tata Steel Ltd.',
                currentPrice: 168.35,
                changePercent: 1.42,
                horizonDays: 3,
                targetPrice: 176.5,
                stopLossPrice: 163.0,
                upsidePercent: 4.8,
                score: 82,
                confidence: 71,
                trust: 65,
                priceHistory: const [10.2, 10.6, 10.4, 10.9],
                lastUpdatedLabel: 'Updated 4m ago',
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await expectLater(
      find.byType(RecommendationCard),
      matchesGoldenFile('goldens/recommendation_card_populated.png'),
    );
  });

  testWidgets('KPI stat row golden', (tester) async {
    await _setGoldenSurface(tester, const Size(360, 120));
    await tester.pumpWidget(
      MaterialApp(
        theme: MraTheme.light(),
        home: Scaffold(
          body: Padding(
            padding: const EdgeInsets.all(MraSpacing.md),
            child: Row(
              key: const Key('kpiStatRow'),
              children: const [
                Expanded(
                  child: KpiStatCard(label: 'Opportunities', value: '18'),
                ),
                SizedBox(width: MraSpacing.md),
                Expanded(
                  child: KpiStatCard(label: 'Avg Trust', value: '76'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await expectLater(
      find.byKey(const Key('kpiStatRow')),
      matchesGoldenFile('goldens/kpi_stat_row.png'),
    );
  });

  testWidgets('sign-in screen (compact viewport) golden', (tester) async {
    await _setGoldenSurface(tester, const Size(390, 844));
    final controller = AuthController(
      repository: _NeverSignsInAuthRepository(),
    );
    await tester.pumpWidget(
      MaterialApp(
        theme: MraTheme.light(),
        home: SignInScreen(controller: controller),
      ),
    );
    await tester.pumpAndSettle();

    await expectLater(
      find.byType(SignInScreen),
      matchesGoldenFile('goldens/sign_in_screen_compact.png'),
    );
  });
}
