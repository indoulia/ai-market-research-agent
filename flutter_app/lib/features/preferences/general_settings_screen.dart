import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../core/api_exception.dart';
import '../../design_system/design_system.dart';
import 'preferences.dart';
import 'preferences_repository.dart';
import 'theme_mode_selector.dart';

enum _LoadState { loading, error, loaded }

/// EPIC-M1.142 — "Settings" screen: appearance/theme, data-refresh
/// display preference, and about/version/data-provider transparency.
/// Notification toggles live on the Quick Preferences tab (M1.142's own
/// screen list mentions notifications under both tabs; duplicating the
/// same switches in two places would be confusing, so this tab links to
/// them instead of repeating them).
class GeneralSettingsScreen extends StatefulWidget {
  final PreferencesRepository? repository;

  const GeneralSettingsScreen({super.key, this.repository});

  @override
  State<GeneralSettingsScreen> createState() => _GeneralSettingsScreenState();
}

class _GeneralSettingsScreenState extends State<GeneralSettingsScreen> {
  late final PreferencesRepository _repository;
  _LoadState _state = _LoadState.loading;
  Preferences _preferences = Preferences.empty;
  ApiException? _error;

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? PreferencesRepository();
    _load();
  }

  Future<void> _load() async {
    setState(() => _state = _LoadState.loading);
    try {
      final preferences = await _repository.fetch();
      setState(() {
        _preferences = preferences;
        _state = _LoadState.loaded;
      });
    } catch (e) {
      setState(() {
        _error = e is ApiException ? e : ApiException.network(e);
        _state = _LoadState.error;
      });
    }
  }

  Future<void> _updateDisplay(DisplayPreferences display) async {
    setState(
      () => _preferences = _preferences.copyWith(displayPreferences: display),
    );
    try {
      await _repository.update(_preferences);
    } catch (_) {
      // Best-effort: appearance still applies locally for this session even
      // if the server-side save fails; no silent data loss to correct for.
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return SingleChildScrollView(
      padding: const EdgeInsets.all(MraSpacing.lg),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 700),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Settings', style: theme.textTheme.headlineSmall),
            const SizedBox(height: MraSpacing.xl),
            // Appearance/refresh depend on M1.141's preferences fetch; About
            // and the QA gallery link below never do, so a failed/slow
            // preferences fetch never blocks access to them.
            _buildDisplaySection(context),
            const SizedBox(height: MraSpacing.xxl),
            Text('About', style: theme.textTheme.labelLarge),
            const SizedBox(height: MraSpacing.sm),
            MraCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'MRA — Market Research Agent',
                    style: theme.textTheme.bodyMedium,
                  ),
                  const SizedBox(height: MraSpacing.xs),
                  Text(
                    'Version 1.0.0',
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                  const SizedBox(height: MraSpacing.sm),
                  Text(
                    'Market data is sourced from Yahoo Finance for research/'
                    'prototyping purposes and is not a claim of licensed '
                    'production market-data redistribution.',
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: MraSpacing.lg),
            OutlinedButton.icon(
              icon: const Icon(Icons.palette_outlined),
              label: const Text('Design system gallery (QA)'),
              onPressed: () => context.push('/dev/gallery'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildDisplaySection(BuildContext context) {
    final theme = Theme.of(context);
    switch (_state) {
      case _LoadState.loading:
        return const MraCard(child: SkeletonCard());
      case _LoadState.error:
        return MraCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Appearance & refresh preferences unavailable',
                style: theme.textTheme.bodyMedium,
              ),
              const SizedBox(height: MraSpacing.xs),
              Text(
                _error?.message ?? 'Something went wrong.',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
              const SizedBox(height: MraSpacing.sm),
              OutlinedButton(onPressed: _load, child: const Text('Retry')),
            ],
          ),
        );
      case _LoadState.loaded:
        final display = _preferences.displayPreferences;
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Appearance', style: theme.textTheme.labelLarge),
            const SizedBox(height: MraSpacing.sm),
            ThemeModeSelector(
              selected: display.themeMode,
              onChanged: (mode) =>
                  _updateDisplay(display.copyWith(themeMode: mode)),
            ),
            const SizedBox(height: MraSpacing.xl),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Show freshness timestamps'),
              subtitle: const Text('Data refresh display preference'),
              value: display.showFreshnessTimestamps,
              onChanged: (v) =>
                  _updateDisplay(display.copyWith(showFreshnessTimestamps: v)),
            ),
            const SizedBox(height: MraSpacing.md),
            OutlinedButton.icon(
              icon: const Icon(Icons.notifications_outlined),
              label: const Text('Manage notification preferences'),
              onPressed: () => DefaultTabController.of(context).animateTo(0),
            ),
          ],
        );
    }
  }
}
