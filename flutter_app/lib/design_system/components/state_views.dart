import 'package:flutter/material.dart';

import '../tokens/mra_spacing.dart';

/// EPIC-M1.133 — shared empty/error/offline state view. Screens must not
/// build ad hoc "nothing here" layouts.
class MraStateView extends StatelessWidget {
  final IconData icon;
  final String title;
  final String? message;
  final String? actionLabel;
  final VoidCallback? onAction;

  const MraStateView({
    super.key,
    required this.icon,
    required this.title,
    this.message,
    this.actionLabel,
    this.onAction,
  });

  const MraStateView.empty({
    super.key,
    this.title = 'Nothing to show yet',
    this.message,
    this.actionLabel,
    this.onAction,
  }) : icon = Icons.inbox_outlined;

  const MraStateView.error({
    super.key,
    this.title = 'Something went wrong',
    this.message,
    this.actionLabel = 'Retry',
    this.onAction,
  }) : icon = Icons.error_outline;

  const MraStateView.offline({
    super.key,
    this.title = "You're offline",
    this.message = 'Showing the last data we had.',
    this.actionLabel = 'Retry',
    this.onAction,
  }) : icon = Icons.wifi_off_outlined;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    // Scrollable instead of a bare Column: when this view is squeezed into a
    // short box (e.g. a compact empty-state slot), content scrolls rather
    // than overflowing.
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(MraSpacing.xxl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 40, color: theme.colorScheme.onSurfaceVariant),
            const SizedBox(height: MraSpacing.lg),
            Text(
              title,
              style: theme.textTheme.titleMedium,
              textAlign: TextAlign.center,
            ),
            if (message != null) ...[
              const SizedBox(height: MraSpacing.sm),
              Text(
                message!,
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
                textAlign: TextAlign.center,
              ),
            ],
            if (actionLabel != null && onAction != null) ...[
              const SizedBox(height: MraSpacing.lg),
              FilledButton(onPressed: onAction, child: Text(actionLabel!)),
            ],
          ],
        ),
      ),
    );
  }
}
