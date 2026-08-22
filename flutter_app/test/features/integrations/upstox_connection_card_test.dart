import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mra_app/core/api_exception.dart';
import 'package:mra_app/design_system/theme/mra_theme.dart';
import 'package:mra_app/features/integrations/upstox_connection_card.dart';
import 'package:mra_app/features/integrations/upstox_repository.dart';
import 'package:mra_app/features/integrations/upstox_status.dart';

Map<String, dynamic> _statusJson({
  bool connected = false,
  bool isExpired = false,
  String? obtainedAt,
  String? expiresAt,
  String environment = 'sandbox',
}) {
  return {
    'connected': connected,
    'isExpired': isExpired,
    'obtainedAt': obtainedAt,
    'expiresAt': expiresAt,
    'environment': environment,
  };
}

class _FakeUpstoxRepository extends UpstoxRepository {
  final Future<Map<String, dynamic>> Function() onFetchStatus;
  final Future<Map<String, dynamic>> Function()? onFetchAuthorization;

  _FakeUpstoxRepository(this.onFetchStatus, {this.onFetchAuthorization});

  @override
  Future<UpstoxStatus> fetchStatus() async =>
      UpstoxStatus.fromJson(await onFetchStatus());

  @override
  Future<UpstoxAuthorization> fetchAuthorization() async =>
      UpstoxAuthorization.fromJson(await onFetchAuthorization!());
}

Widget _wrap(Widget child) => MaterialApp(
  theme: MraTheme.light(),
  home: Scaffold(body: child),
);

void main() {
  testWidgets(
    'never-connected status shows "Not connected" and a Connect button',
    (tester) async {
      final repo = _FakeUpstoxRepository(() async => _statusJson());
      await tester.pumpWidget(_wrap(UpstoxConnectionCard(repository: repo)));
      await tester.pumpAndSettle();

      expect(find.text('Not connected'), findsOneWidget);
      expect(find.text('Connect Upstox'), findsOneWidget);
      expect(find.text('Reconnect Upstox'), findsNothing);
    },
  );

  testWidgets(
    'a valid connection shows "Connected" and hides the connect button',
    (tester) async {
      final repo = _FakeUpstoxRepository(
        () async => _statusJson(
          connected: true,
          obtainedAt: '2026-08-20T10:00:00Z',
          expiresAt: '2026-08-22T10:00:00Z',
        ),
      );
      await tester.pumpWidget(_wrap(UpstoxConnectionCard(repository: repo)));
      await tester.pumpAndSettle();

      expect(find.text('Connected'), findsOneWidget);
      expect(find.textContaining('Connected since'), findsOneWidget);
      expect(find.text('Connect Upstox'), findsNothing);
    },
  );

  testWidgets(
    'an expired token shows "Connection expired" and a Reconnect button',
    (tester) async {
      final repo = _FakeUpstoxRepository(
        () async => _statusJson(
          connected: false,
          isExpired: true,
          obtainedAt: '2026-08-10T10:00:00Z',
          expiresAt: '2026-08-11T10:00:00Z',
        ),
      );
      await tester.pumpWidget(_wrap(UpstoxConnectionCard(repository: repo)));
      await tester.pumpAndSettle();

      expect(find.text('Connection expired'), findsOneWidget);
      expect(find.text('Reconnect Upstox'), findsOneWidget);
    },
  );

  testWidgets(
    'tapping Connect fetches an authorization URL and opens it via the injected launcher',
    (tester) async {
      Uri? launched;
      final repo = _FakeUpstoxRepository(
        () async => _statusJson(),
        onFetchAuthorization: () async => {
          'authorizationUrl':
              'https://api.upstox.com/v2/login/authorization/dialog?x=1',
          'state': 'abc123',
          'expiresAt': '2026-08-22T10:10:00Z',
        },
      );
      await tester.pumpWidget(
        _wrap(
          UpstoxConnectionCard(
            repository: repo,
            launchUrl: (uri) async {
              launched = uri;
              return true;
            },
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Connect Upstox'));
      await tester.pumpAndSettle();

      expect(
        launched,
        Uri.parse('https://api.upstox.com/v2/login/authorization/dialog?x=1'),
      );
      expect(find.textContaining("Couldn't open"), findsNothing);
    },
  );

  testWidgets('a failed launch surfaces an inline error without crashing', (
    tester,
  ) async {
    final repo = _FakeUpstoxRepository(
      () async => _statusJson(),
      onFetchAuthorization: () async => {
        'authorizationUrl':
            'https://api.upstox.com/v2/login/authorization/dialog?x=1',
        'state': 'abc123',
        'expiresAt': '2026-08-22T10:10:00Z',
      },
    );
    await tester.pumpWidget(
      _wrap(
        UpstoxConnectionCard(repository: repo, launchUrl: (_) async => false),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Connect Upstox'));
    await tester.pumpAndSettle();

    expect(find.textContaining("Couldn't open"), findsOneWidget);
  });

  testWidgets(
    'the authorize call failing (e.g. Upstox not configured) surfaces the server message',
    (tester) async {
      final repo = _FakeUpstoxRepository(
        () async => _statusJson(),
        onFetchAuthorization: () async {
          throw const ApiException(
            code: 'MRA_UPSTOX_NOT_CONFIGURED',
            message: 'Upstox OAuth is not configured.',
          );
        },
      );
      await tester.pumpWidget(_wrap(UpstoxConnectionCard(repository: repo)));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Connect Upstox'));
      await tester.pumpAndSettle();

      expect(find.text('Upstox OAuth is not configured.'), findsOneWidget);
    },
  );

  testWidgets(
    'a status fetch failure renders the shared MraStateView.error, and Retry recovers',
    (tester) async {
      var attempt = 0;
      final repo = _FakeUpstoxRepository(() async {
        attempt++;
        if (attempt == 1) {
          throw const ApiException(code: 'MRA_INTERNAL', message: 'Boom');
        }
        return _statusJson();
      });
      await tester.pumpWidget(_wrap(UpstoxConnectionCard(repository: repo)));
      await tester.pumpAndSettle();

      expect(find.text('Upstox connection status unavailable'), findsOneWidget);

      await tester.tap(find.text('Retry'));
      await tester.pumpAndSettle();

      expect(find.text('Not connected'), findsOneWidget);
    },
  );

  testWidgets('tapping the refresh icon re-fetches status', (tester) async {
    var connected = false;
    final repo = _FakeUpstoxRepository(
      () async => _statusJson(connected: connected),
    );
    await tester.pumpWidget(_wrap(UpstoxConnectionCard(repository: repo)));
    await tester.pumpAndSettle();
    expect(find.text('Not connected'), findsOneWidget);

    connected = true;
    await tester.tap(find.byTooltip('Refresh status'));
    await tester.pumpAndSettle();

    expect(find.text('Connected'), findsOneWidget);
  });
}
