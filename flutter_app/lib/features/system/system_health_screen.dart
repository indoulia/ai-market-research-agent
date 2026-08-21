import 'package:flutter/material.dart';

import '../../core/api_exception.dart';
import '../../design_system/design_system.dart';
import 'data_freshness_item.dart';
import 'provider_status.dart';
import 'system_event.dart';
import 'system_health_summary.dart';
import 'system_repository.dart';

enum _LoadState { loading, error, loaded }

/// EPIC-M3.11 — "System" tab of the Settings destination: a compact
/// operational view of MRA data/provider health, freshness, latency and
/// fallback state, so a user can distinguish a market condition from an
/// information-system degradation (this EPIC's own Objective). Read-only:
/// nothing on this screen writes anything, matching the "health state is
/// read-only to normal users" AC, and no provider credential/config is
/// ever rendered (the API surface itself never serializes one).
class SystemHealthScreen extends StatefulWidget {
  final SystemRepository? repository;

  const SystemHealthScreen({super.key, this.repository});

  @override
  State<SystemHealthScreen> createState() => _SystemHealthScreenState();
}

class _SystemHealthScreenState extends State<SystemHealthScreen> {
  late final SystemRepository _repository;
  _LoadState _state = _LoadState.loading;
  SystemHealthSummary? _health;
  List<ProviderStatus> _providers = const [];
  List<DataFreshnessItem> _freshness = const [];
  List<SystemEvent> _events = const [];
  String? _eventsCursor;
  bool _loadingMoreEvents = false;
  ApiException? _error;

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? SystemRepository();
    _load();
  }

  Future<void> _load() async {
    setState(() => _state = _LoadState.loading);
    try {
      final results = await Future.wait([
        _repository.fetchHealth(),
        _repository.fetchProviders(),
        _repository.fetchDataFreshness(),
        _repository.fetchEvents(),
      ]);
      final eventsPage = results[3] as SystemEventsPage;
      setState(() {
        _health = results[0] as SystemHealthSummary;
        _providers = results[1] as List<ProviderStatus>;
        _freshness = results[2] as List<DataFreshnessItem>;
        _events = eventsPage.items;
        _eventsCursor = eventsPage.nextCursor;
        _state = _LoadState.loaded;
      });
    } catch (e) {
      setState(() {
        _error = e is ApiException ? e : ApiException.network(e);
        _state = _LoadState.error;
      });
    }
  }

  Future<void> _loadMoreEvents() async {
    if (_eventsCursor == null || _loadingMoreEvents) return;
    setState(() => _loadingMoreEvents = true);
    try {
      final page = await _repository.fetchEvents(cursor: _eventsCursor);
      setState(() {
        _events = [..._events, ...page.items];
        _eventsCursor = page.nextCursor;
        _loadingMoreEvents = false;
      });
    } catch (_) {
      setState(() => _loadingMoreEvents = false);
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
        return _buildLoaded(context);
    }
  }

  Widget _buildLoaded(BuildContext context) {
    final theme = Theme.of(context);
    final health = _health!;
    return RefreshIndicator(
      onRefresh: _load,
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(MraSpacing.lg),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 1200),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'System & provider health',
                style: theme.textTheme.headlineSmall,
              ),
              const SizedBox(height: MraSpacing.sm),
              Text(
                'An operational view of MRA data sources — not investment '
                'or trading guidance. Degraded or stale data here means the '
                'information system, not the market, may be the cause of an '
                'unexpected result.',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
              const SizedBox(height: MraSpacing.lg),
              _buildHealthHeader(context, health),
              const SizedBox(height: MraSpacing.xl),
              Text('Providers', style: theme.textTheme.titleMedium),
              const SizedBox(height: MraSpacing.sm),
              _buildProviderGrid(context),
              const SizedBox(height: MraSpacing.xl),
              Text(
                'Data freshness by capability',
                style: theme.textTheme.titleMedium,
              ),
              const SizedBox(height: MraSpacing.sm),
              _buildFreshnessList(context),
              const SizedBox(height: MraSpacing.xl),
              Text('Incident history', style: theme.textTheme.titleMedium),
              const SizedBox(height: MraSpacing.sm),
              _buildEventsList(context),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildHealthHeader(BuildContext context, SystemHealthSummary health) {
    final theme = Theme.of(context);
    return MraCard(
      child: Padding(
        padding: const EdgeInsets.all(MraSpacing.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Wrap(
              spacing: MraSpacing.sm,
              runSpacing: MraSpacing.sm,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                MraChip(label: health.status, tone: _healthTone(health.status)),
                MraChip(
                  label: 'Market: ${_sessionLabel(health.marketSession)}',
                  tone: MraChipTone.neutral,
                ),
                MraChip(
                  label: health.databaseOk
                      ? 'Database OK'
                      : 'Database unreachable',
                  tone: health.databaseOk
                      ? MraChipTone.positive
                      : MraChipTone.error,
                ),
                if (health.activeOutageCount > 0)
                  MraChip(
                    label: '${health.activeOutageCount} active outage(s)',
                    tone: MraChipTone.warning,
                  ),
              ],
            ),
            const SizedBox(height: MraSpacing.sm),
            Text(
              'Checked ${_formatDateTime(health.checkedAt)} · API ${health.apiVersion}',
              style: theme.textTheme.labelSmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildProviderGrid(BuildContext context) {
    if (_providers.isEmpty) {
      return const MraStateView.empty(
        message: 'No provider activity has been recorded yet.',
      );
    }
    return MraDenseTable(
      columns: const [
        MraColumn('Provider'),
        MraColumn('Capability'),
        MraColumn('Status'),
        MraColumn('Last success'),
        MraColumn('Latency'),
        MraColumn('Freshness'),
        MraColumn('Fallback'),
        MraColumn('Quality'),
      ],
      rows: _providers.map((p) => _providerRow(context, p)).toList(),
    );
  }

  List<Widget> _providerRow(BuildContext context, ProviderStatus provider) {
    return [
      Text(provider.providerId),
      Text(provider.capability),
      MraChip(
        label: provider.status,
        tone: _providerStatusTone(provider.status),
      ),
      Text(
        provider.lastSuccessAt == null
            ? '—'
            : _formatDateTime(provider.lastSuccessAt!),
      ),
      Text(provider.latencyMs == null ? '—' : '${provider.latencyMs} ms'),
      MraChip(
        label: provider.freshness.isFresh ? 'Fresh' : 'Stale',
        tone: provider.freshness.isFresh
            ? MraChipTone.positive
            : MraChipTone.warning,
      ),
      provider.fallbackActive
          ? const MraChip(label: 'Active', tone: MraChipTone.warning)
          : Text('—', style: Theme.of(context).textTheme.bodyMedium),
      Text(
        provider.qualityScore == null
            ? '—'
            : '${(provider.qualityScore! * 100).toStringAsFixed(0)}%',
      ),
    ];
  }

  Widget _buildFreshnessList(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: _freshness
          .map(
            (item) => Padding(
              padding: const EdgeInsets.symmetric(vertical: MraSpacing.xs),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      item.capability,
                      style: theme.textTheme.bodyMedium,
                    ),
                  ),
                  Expanded(
                    child: Text(
                      item.lastSuccessAt == null
                          ? 'No successful fetch recorded'
                          : 'Last success ${_formatDateTime(item.lastSuccessAt!)}',
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ),
                  MraChip(
                    label: item.isFresh ? 'Fresh' : 'Stale',
                    tone: item.isFresh
                        ? MraChipTone.positive
                        : MraChipTone.warning,
                  ),
                ],
              ),
            ),
          )
          .toList(),
    );
  }

  Widget _buildEventsList(BuildContext context) {
    if (_events.isEmpty) {
      return const MraStateView.empty(
        message:
            'No provider outages, unexpected closures or latency '
            'degradations have been recorded.',
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (var i = 0; i < _events.length; i++)
          TimelineEventRow(
            title: _events[i].description,
            subtitle: _events[i].type,
            timestampLabel: _formatDateTime(_events[i].occurredAt),
            tone: _eventTone(_events[i]),
            isLast: i == _events.length - 1 && _eventsCursor == null,
          ),
        if (_eventsCursor != null)
          Padding(
            padding: const EdgeInsets.only(top: MraSpacing.sm),
            child: OutlinedButton(
              onPressed: _loadingMoreEvents ? null : _loadMoreEvents,
              child: Text(_loadingMoreEvents ? 'Loading…' : 'Load more'),
            ),
          ),
      ],
    );
  }

  MraChipTone _healthTone(String status) {
    switch (status) {
      case 'OK':
        return MraChipTone.positive;
      case 'DEGRADED':
        return MraChipTone.warning;
      case 'OUTAGE':
        return MraChipTone.error;
      default:
        return MraChipTone.neutral;
    }
  }

  MraChipTone _providerStatusTone(String status) {
    switch (status) {
      case 'OK':
        return MraChipTone.positive;
      case 'WEAK':
        return MraChipTone.warning;
      default:
        return MraChipTone.neutral;
    }
  }

  MraTimelineTone _eventTone(SystemEvent event) {
    switch (event.severity) {
      case 'TOTAL':
        return MraTimelineTone.error;
      case 'PARTIAL':
      case 'WARNING':
        return MraTimelineTone.warning;
      default:
        return MraTimelineTone.neutral;
    }
  }

  String _sessionLabel(String session) => switch (session) {
    'PRE_MARKET' => 'Pre-market',
    'MARKET_HOURS' => 'Open',
    'POST_MARKET' => 'Post-market',
    _ => 'Closed',
  };

  String _formatDateTime(DateTime value) {
    final local = value.toLocal();
    final date =
        '${local.year}-${local.month.toString().padLeft(2, '0')}-${local.day.toString().padLeft(2, '0')}';
    final time =
        '${local.hour.toString().padLeft(2, '0')}:${local.minute.toString().padLeft(2, '0')}';
    return '$date $time';
  }
}
