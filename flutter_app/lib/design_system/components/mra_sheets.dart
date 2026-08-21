import 'package:flutter/material.dart';

import '../tokens/mra_spacing.dart';

/// EPIC-M1.133 — shared bottom sheet chrome (drag handle, title, padded
/// body) so every sheet across the app looks the same.
Future<T?> showMraBottomSheet<T>({
  required BuildContext context,
  required String title,
  required WidgetBuilder builder,
}) {
  final theme = Theme.of(context);
  return showModalBottomSheet<T>(
    context: context,
    showDragHandle: true,
    isScrollControlled: true,
    backgroundColor: theme.colorScheme.surface,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
    ),
    builder: (context) => SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(
          MraSpacing.lg,
          MraSpacing.sm,
          MraSpacing.lg,
          MraSpacing.lg,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: theme.textTheme.titleMedium),
            const SizedBox(height: MraSpacing.md),
            builder(context),
          ],
        ),
      ),
    ),
  );
}

/// EPIC-M1.133 — shared dialog chrome for confirmations/detail popovers.
Future<T?> showMraDialog<T>({
  required BuildContext context,
  required String title,
  required Widget content,
  List<Widget> actions = const [],
}) {
  return showDialog<T>(
    context: context,
    builder: (context) =>
        AlertDialog(title: Text(title), content: content, actions: actions),
  );
}
