import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import 'app_shell/app_router.dart';
import 'core/auth/auth_controller.dart';
import 'design_system/theme/mra_theme.dart';

void main() {
  runApp(const MraApp());
}

/// EPIC-M1.146 — the real app (unlike tests) always gates on a real
/// [AuthController], so it builds its own router rather than reusing the
/// no-auth [appRouter] singleton.
class MraApp extends StatefulWidget {
  /// Test-only seam: pass a pre-configured [AuthController] (e.g. already
  /// `authenticated`) to skip real session restoration. Production always
  /// omits this and gets a real, restoring controller.
  final AuthController? authController;

  const MraApp({super.key, this.authController});

  @override
  State<MraApp> createState() => _MraAppState();
}

class _MraAppState extends State<MraApp> {
  late final AuthController _authController;
  late final GoRouter _router;
  bool _ownsAuthController = false;

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
    _router = buildAppRouter(authController: _authController);
  }

  @override
  void dispose() {
    if (_ownsAuthController) _authController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      title: 'MRA',
      debugShowCheckedModeBanner: false,
      theme: MraTheme.light(),
      darkTheme: MraTheme.dark(),
      routerConfig: _router,
    );
  }
}
