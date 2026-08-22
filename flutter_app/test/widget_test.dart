import 'package:flutter_test/flutter_test.dart';

import 'package:mra_app/core/app_bootstrap_repository.dart';
import 'package:mra_app/core/app_compatibility.dart';
import 'package:mra_app/core/auth/auth_controller.dart';
import 'package:mra_app/main.dart';

/// A default `MraApp()` calls a bare, un-injected `AppBootstrapRepository`
/// (real `ApiClient`, real network) as part of its EPIC-M1.144 launch
/// compatibility check. Every test below injects this instead so it never
/// depends on a running server.
class _FakeBootstrapRepository extends AppBootstrapRepository {
  final String contractVersion;
  _FakeBootstrapRepository({this.contractVersion = kSupportedContractVersion});

  @override
  Future<AppBootstrapInfo> fetch() async => AppBootstrapInfo(
    apiVersion: 'v1',
    contractVersion: contractVersion,
    capabilities: const {},
  );
}

void main() {
  testWidgets('App boots into the Home destination of the app shell', (
    tester,
  ) async {
    final authController = AuthController()..status = AuthStatus.authenticated;
    await tester.pumpWidget(
      MraApp(
        authController: authController,
        bootstrapRepository: _FakeBootstrapRepository(),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Marksy'), findsOneWidget);
    expect(find.text('Home'), findsWidgets);
  });

  testWidgets(
    'EPIC-M1.144: an incompatible server contract blocks the app shell',
    (tester) async {
      final authController = AuthController()
        ..status = AuthStatus.authenticated;
      await tester.pumpWidget(
        MraApp(
          authController: authController,
          bootstrapRepository: _FakeBootstrapRepository(
            contractVersion: '1999-01-01',
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Update required'), findsOneWidget);
      expect(find.text('Home'), findsNothing);
    },
  );
}
