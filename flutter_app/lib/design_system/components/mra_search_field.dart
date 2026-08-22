import 'package:flutter/material.dart';

/// EPIC-M1.133 — shared search entry field for global/screen-level search.
/// EPIC-171 follow-up — [prefixIcon]/[onSubmitted] let this cover
/// submit-to-filter fields (e.g. Dashboard's sector filter) too, so those
/// screens reuse this instead of hand-rolling an identically-styled TextField.
class MraSearchField extends StatelessWidget {
  final String hintText;
  final ValueChanged<String>? onChanged;
  final ValueChanged<String>? onSubmitted;
  final VoidCallback? onClear;
  final TextEditingController? controller;
  final IconData prefixIcon;

  const MraSearchField({
    super.key,
    this.hintText = 'Search',
    this.onChanged,
    this.onSubmitted,
    this.onClear,
    this.controller,
    this.prefixIcon = Icons.search,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return TextField(
      controller: controller,
      onChanged: onChanged,
      onSubmitted: onSubmitted,
      textInputAction: TextInputAction.search,
      style: theme.textTheme.bodyMedium,
      decoration: InputDecoration(
        hintText: hintText,
        prefixIcon: Icon(prefixIcon, size: 20),
        suffixIcon: onClear == null
            ? null
            : IconButton(
                icon: const Icon(Icons.close, size: 18),
                tooltip: 'Clear search',
                onPressed: onClear,
              ),
        filled: true,
        fillColor: theme.colorScheme.surfaceContainerHigh,
        contentPadding: const EdgeInsets.symmetric(vertical: 0, horizontal: 12),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide.none,
        ),
        isDense: true,
      ),
    );
  }
}
