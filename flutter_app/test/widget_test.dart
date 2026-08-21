import 'package:flutter_test/flutter_test.dart';

import 'package:mra_app/main.dart';

void main() {
  testWidgets('App boots into the Home destination of the app shell', (
    tester,
  ) async {
    await tester.pumpWidget(const MraApp());
    await tester.pumpAndSettle();

    expect(find.text('MRA'), findsOneWidget);
    expect(find.text('Home'), findsWidgets);
  });
}
