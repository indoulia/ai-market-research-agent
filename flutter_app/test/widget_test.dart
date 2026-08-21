import 'package:flutter_test/flutter_test.dart';

import 'package:mra_app/core/auth/auth_controller.dart';
import 'package:mra_app/main.dart';

void main() {
  testWidgets('App boots into the Home destination of the app shell', (
    tester,
  ) async {
    final authController = AuthController()..status = AuthStatus.authenticated;
    await tester.pumpWidget(MraApp(authController: authController));
    await tester.pumpAndSettle();

    expect(find.text('MRA'), findsOneWidget);
    expect(find.text('Home'), findsWidgets);
  });
}
