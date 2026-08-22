import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../core/auth/auth_controller.dart';
import '../../design_system/design_system.dart';

/// EPIC-M1.146 — minimal, compact sign-in screen. Only collects a user id:
/// M1.145's backend is currently a self-asserted `CredentialVerifier`
/// placeholder (no password/OAuth identity provider exists yet, per that
/// epic's own completion report) — a password field here would imply a
/// security property this platform doesn't actually have. UX rules: no
/// marketing artwork, compact form, one strong primary action.
class SignInScreen extends StatefulWidget {
  final AuthController controller;

  /// Where to navigate after a successful sign-in (the deep link the user
  /// originally tried to reach, preserved by the router's redirect).
  final String? redirectTo;

  const SignInScreen({super.key, required this.controller, this.redirectTo});

  @override
  State<SignInScreen> createState() => _SignInScreenState();
}

class _SignInScreenState extends State<SignInScreen> {
  final TextEditingController _userIdController = TextEditingController();
  bool _submitting = false;

  @override
  void dispose() {
    _userIdController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final userId = _userIdController.text.trim();
    if (userId.isEmpty) return;
    setState(() => _submitting = true);
    final ok = await widget.controller.signIn(userId);
    if (!mounted) return;
    setState(() => _submitting = false);
    if (ok) {
      context.go(widget.redirectTo ?? '/home');
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(MraSpacing.xl),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 360),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Sign in', style: theme.textTheme.headlineSmall),
                const SizedBox(height: MraSpacing.xs),
                Text(
                  'MRA — Market Research Agent',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
                if (widget.controller.status == AuthStatus.sessionExpired) ...[
                  const SizedBox(height: MraSpacing.lg),
                  MraChip(
                    label: 'Your session expired — sign in again',
                    tone: MraChipTone.warning,
                    icon: Icons.schedule,
                  ),
                ],
                const SizedBox(height: MraSpacing.xxl),
                TextField(
                  controller: _userIdController,
                  autofocus: true,
                  textInputAction: TextInputAction.done,
                  onSubmitted: (_) => _submit(),
                  decoration: const InputDecoration(
                    labelText: 'User ID',
                    border: OutlineInputBorder(),
                  ),
                ),
                if (widget.controller.lastError != null) ...[
                  const SizedBox(height: MraSpacing.sm),
                  Text(
                    widget.controller.lastError!,
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.error,
                    ),
                  ),
                ],
                const SizedBox(height: MraSpacing.lg),
                // EPIC-M3.13 — the loading spinner replaces the "Continue"
                // Text child while submitting; without this Semantics
                // wrapper a screen reader would announce a nameless button
                // during that window (icons/visuals must never replace
                // necessary text without an accessible label).
                Semantics(
                  button: true,
                  enabled: !_submitting,
                  label: _submitting ? 'Continue, submitting' : 'Continue',
                  child: SizedBox(
                    width: double.infinity,
                    child: ExcludeSemantics(
                      child: FilledButton(
                        onPressed: _submitting ? null : _submit,
                        child: _submitting
                            ? const SizedBox(
                                width: 20,
                                height: 20,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                  color: Colors.white,
                                ),
                              )
                            : const Text('Continue'),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
