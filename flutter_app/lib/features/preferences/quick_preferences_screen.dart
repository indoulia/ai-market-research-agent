import 'package:flutter/material.dart';

import '../../core/api_exception.dart';
import '../../design_system/design_system.dart';
import 'chip_list_editor.dart';
import 'preferences.dart';
import 'preferences_repository.dart';

enum _LoadState { loading, error, loaded }

enum _SaveState { idle, saving, saved, failed }

const _bucketOptions = [
  MraFilterOption('LARGE_CAP', 'Large cap'),
  MraFilterOption('MID_CAP', 'Mid cap'),
  MraFilterOption('SMALL_CAP', 'Small cap'),
];

/// EPIC-M1.142 — "Quick Preferences" screen: default horizon, market-cap
/// scope, watchlist, sector scope, and notification toggles, as one
/// compact form (UX rule: "compact forms, not long settings pages").
class QuickPreferencesScreen extends StatefulWidget {
  final PreferencesRepository? repository;

  const QuickPreferencesScreen({super.key, this.repository});

  @override
  State<QuickPreferencesScreen> createState() => _QuickPreferencesScreenState();
}

class _QuickPreferencesScreenState extends State<QuickPreferencesScreen> {
  late final PreferencesRepository _repository;
  _LoadState _state = _LoadState.loading;
  _SaveState _saveState = _SaveState.idle;
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

  Future<void> _save(Preferences updated) async {
    setState(() {
      _preferences = updated;
      _saveState = _SaveState.saving;
    });
    try {
      final saved = await _repository.update(updated);
      if (!mounted) return;
      setState(() {
        _preferences = saved;
        _saveState = _SaveState.saved;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _saveState = _SaveState.failed);
    }
  }

  @override
  Widget build(BuildContext context) {
    switch (_state) {
      case _LoadState.loading:
        return const Padding(
          padding: EdgeInsets.all(MraSpacing.lg),
          child: MraCard(child: SkeletonCard()),
        );
      case _LoadState.error:
        return MraStateView.error(message: _error?.message, onAction: _load);
      case _LoadState.loaded:
        return _buildForm(context);
    }
  }

  Widget _buildForm(BuildContext context) {
    final theme = Theme.of(context);
    return SingleChildScrollView(
      padding: const EdgeInsets.all(MraSpacing.lg),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 700),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text('Quick Preferences', style: theme.textTheme.headlineSmall),
                _SaveStatusLabel(state: _saveState),
              ],
            ),
            const SizedBox(height: MraSpacing.xl),
            Text('Default horizon', style: theme.textTheme.labelLarge),
            const SizedBox(height: MraSpacing.sm),
            HorizonSelector(
              horizonsDays: const [1, 3, 5, 7],
              selectedDays: _preferences.defaultHorizon,
              onChanged: (v) => _save(_preferences.copyWith(defaultHorizon: v)),
            ),
            const SizedBox(height: MraSpacing.xl),
            Text('Market-cap scope', style: theme.textTheme.labelLarge),
            const SizedBox(height: MraSpacing.sm),
            MraFilterBar(
              options: _bucketOptions,
              selectedIds: _preferences.marketCapBuckets.toSet(),
              onToggle: (id) {
                final buckets = {..._preferences.marketCapBuckets};
                if (buckets.contains(id)) {
                  buckets.remove(id);
                } else {
                  buckets.add(id);
                }
                _save(
                  _preferences.copyWith(marketCapBuckets: buckets.toList()),
                );
              },
            ),
            const SizedBox(height: MraSpacing.xl),
            ChipListEditor(
              label: 'Watchlist',
              hintText: 'Add symbol (e.g. TATASTEEL)',
              values: _preferences.watchlist,
              onChanged: (v) => _save(_preferences.copyWith(watchlist: v)),
            ),
            const SizedBox(height: MraSpacing.xl),
            ChipListEditor(
              label: 'Sectors',
              hintText: 'Add sector (e.g. Materials)',
              values: _preferences.sectors,
              onChanged: (v) => _save(_preferences.copyWith(sectors: v)),
            ),
            const SizedBox(height: MraSpacing.xl),
            Text('Notifications', style: theme.textTheme.labelLarge),
            const SizedBox(height: MraSpacing.xs),
            Text(
              'Selected alert types are enabled; tap to mute.',
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: MraSpacing.sm),
            Wrap(
              spacing: MraSpacing.sm,
              runSpacing: MraSpacing.sm,
              children: AlertType.all.map((type) {
                final muted = _preferences.notificationPreferences.isMuted(
                  type,
                );
                return MraChip(
                  label: AlertType.label(type),
                  selected: !muted,
                  tone: muted ? MraChipTone.neutral : MraChipTone.positive,
                  onTap: () => _save(
                    _preferences.copyWith(
                      notificationPreferences: _preferences
                          .notificationPreferences
                          .toggleMuted(type),
                    ),
                  ),
                );
              }).toList(),
            ),
          ],
        ),
      ),
    );
  }
}

class _SaveStatusLabel extends StatelessWidget {
  final _SaveState state;
  const _SaveStatusLabel({required this.state});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return switch (state) {
      _SaveState.idle => const SizedBox.shrink(),
      _SaveState.saving => Text('Saving…', style: theme.textTheme.labelSmall),
      _SaveState.saved => Text(
        'Saved',
        style: theme.textTheme.labelSmall?.copyWith(
          color: MraColorScheme.of(context).positive,
        ),
      ),
      _SaveState.failed => Text(
        'Save failed',
        style: theme.textTheme.labelSmall?.copyWith(
          color: MraColorScheme.of(context).error,
        ),
      ),
    };
  }
}
