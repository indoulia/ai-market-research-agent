import 'package:flutter/material.dart';

/// EPIC-M1.133 — shared toast/snackbar feedback helper so messaging styling
/// is consistent (icon + message, theme-driven colors from [MraTheme]).
void showMraToast(
  BuildContext context,
  String message, {
  bool isError = false,
  SnackBarAction? action,
}) {
  final theme = Theme.of(context);
  ScaffoldMessenger.of(context).clearSnackBars();
  ScaffoldMessenger.of(context).showSnackBar(
    SnackBar(
      content: Row(
        children: [
          Icon(
            isError ? Icons.error_outline : Icons.check_circle_outline,
            size: 18,
            color: theme.colorScheme.onInverseSurface,
          ),
          const SizedBox(width: 8),
          Expanded(child: Text(message)),
        ],
      ),
      action: action,
    ),
  );
}
