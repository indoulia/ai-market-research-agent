import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import 'app_shell/app_router.dart';
import 'app_shell/contract_incompatible_screen.dart';
import 'core/app_bootstrap_repository.dart';
import 'core/app_compatibility.dart';
import 'core/auth/auth_controller.dart';
import 'design_system/theme/mra_theme.dart';

void main() {
  runApp(const MraApp());
}

enum _CompatibilityState { checking, compatible, incompatible }

/// EPIC-M1.146 — the real app (unlike tests) always gates on a real
/// [AuthController], so it builds its own router rather than reusing the
/// no-auth [appRouter] singleton.
///
/// EPIC-M1.144 — also confirms `/app/bootstrap`'s `contractVersion` matches
/// this build's [kSupportedContractVersion] before ever trusting the rest
/// of the API. A network/server failure at this check is treated as
/// non-fatal (`compatible`) rather than blocking launch — this app still
/// has value offline/degraded (Scope: "Offline/reconnect behavior where
/// supported"), and compatibility is only enforced once the server has
/// actually *confirmed* a mismatch, never merely because it didn't answer.
class MraApp extends StatefulWidget {
  /// Test-only seam: pass a pre-configured [AuthController] (e.g. already
  /// `authenticated`) to skip real session restoration. Production always
  /// omits this and gets a real, restoring controller.
  final AuthController? authController;

  /// Test-only seam for the bootstrap/compatibility check, mirroring
  /// [authController].
  final AppBootstrapRepository? bootstrapRepository;

  const MraApp({super.key, this.authController, this.bootstrapRepository});

  @override
  State<MraApp> createState() => _MraAppState();
}

class _MraAppState extends State<MraApp> {
  late final AuthController _authController;
  late final GoRouter _router;
  late final AppBootstrapRepository _bootstrapRepository;
  bool _ownsAuthController = false;

  _CompatibilityState _compatibility = _CompatibilityState.checking;
  String? _serverContractVersion;

  @override
  void initState() {
    super.initState();
    final injected = widget.authController;
    if (injected != null) {
      _authController = injected;
    } else {
      _ownsAuthController = true;
      _authController = AuthController();
      _authController.restore();
    }
    // The actual path the browser/platform reports as the starting route
    // (a bookmarked deep link, a page refresh) — see app_router.dart's
    // `initialDeepLink` doc for why this must be threaded through rather
    // than letting GoRouter's hardcoded `/splash` initialLocation drop it.
    final initialDeepLink = WidgetsBinding.instance.platformDispatcher.defaultRouteName;
    _router = buildAppRouter(
      authController: _authController,
      initialDeepLink: initialDeepLink,
    );
    _bootstrapRepository =
        widget.bootstrapRepository ?? AppBootstrapRepository();
    _checkCompatibility();
  }

  Future<void> _checkCompatibility() async {
    try {
      final info = await _bootstrapRepository.fetch();
      final status = checkContractCompatibility(info.contractVersion);
      if (!mounted) return;
      setState(() {
        _serverContractVersion = info.contractVersion;
        _compatibility = status == AppCompatibilityStatus.incompatible
            ? _CompatibilityState.incompatible
            : _CompatibilityState.compatible;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _compatibility = _CompatibilityState.compatible);
    }
  }

  @override
  void dispose() {
    if (_ownsAuthController) _authController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_compatibility == _CompatibilityState.incompatible) {
      return MaterialApp(
        title: 'MRA',
        debugShowCheckedModeBanner: false,
        theme: MraTheme.light(),
        darkTheme: MraTheme.dark(),
        home: ContractIncompatibleScreen(
          serverContractVersion: _serverContractVersion,
        ),
      );
    }
    return MaterialApp.router(
      title: 'MRA',
      debugShowCheckedModeBanner: false,
      theme: MraTheme.light(),
      darkTheme: MraTheme.dark(),
      routerConfig: _router,
    );
  }
}
