import 'package:flutter/material.dart';

import 'preferences.dart';

/// EPIC-M1.142 — appearance/theme choice, a compact `ChoiceChip` row
/// matching `HorizonSelector`'s established pattern rather than a full
/// settings-page dropdown.
class ThemeModeSelector extends StatelessWidget {
  final AppThemeMode selected;
  final ValueChanged<AppThemeMode> onChanged;

  const ThemeModeSelector({
    super.key,
    required this.selected,
    required this.onChanged,
  });

  String _label(AppThemeMode mode) => switch (mode) {
    AppThemeMode.system => 'System',
    AppThemeMode.light => 'Light',
    AppThemeMode.dark => 'Dark',
  };

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 8,
      children: AppThemeMode.values.map((mode) {
        return ChoiceChip(
          label: Text(_label(mode)),
          selected: selected == mode,
          onSelected: (_) => onChanged(mode),
        );
      }).toList(),
    );
  }
}
