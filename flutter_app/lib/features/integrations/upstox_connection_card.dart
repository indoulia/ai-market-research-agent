import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart' as url_launcher;

import '../../core/api_exception.dart';
import '../../design_system/design_system.dart';
import 'upstox_repository.dart';
import 'upstox_status.dart';

enum _LoadState { loading, error, loaded }

/// EPIC-MARKSY-0001 (fast-follow) — Settings-area card that closes the gap
/// #302's own flow diagram calls step one ("Marksy local UI -> Login with
/// Upstox"): that EPIC shipped the backend OAuth flow
/// (`/integrations/upstox/{authorize,status}`) but no screen ever called
/// it. Shows the current connection status and, when not connected (or
/// expired), a button that fetches a fresh authorization URL and opens it
/// in the system browser -- the OAuth exchange itself happens entirely
/// server-side via Upstox's redirect to the backend's own `/callback`
/// (a browser-only HTML landing page, never called from this app), so
/// there is no way for this card to know the moment that finishes; a
/// manual refresh action lets the user confirm once they return.
class UpstoxConnectionCard extends StatefulWidget {
  final UpstoxRepository? repository;

  /// Test-only seam: real usage always opens the system browser via
  /// `url_launcher`; tests inject a fake to assert the URL without a real
  /// platform launch (which throws in the widget-test environment).
  final Future<bool> Function(Uri)? launchUrl;

  const UpstoxConnectionCard({super.key, this.repository, this.launchUrl});

  @override
  State<UpstoxConnectionCard> createState() => _UpstoxConnectionCardState();
}

class _UpstoxConnectionCardState extends State<UpstoxConnectionCard> {
  late final UpstoxRepository _repository;
  late final Future<bool> Function(Uri) _launchUrl;

  _LoadState _state = _LoadState.loading;
  ApiException? _error;
  UpstoxStatus? _status;
  bool _connecting = false;
  String? _connectError;

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? UpstoxRepository();
    _launchUrl =
        widget.launchUrl ??
        (uri) => url_launcher.launchUrl(
          uri,
          mode: url_launcher.LaunchMode.externalApplication,
        );
    _load();
  }

  Future<void> _load() async {
    setState(() => _state = _LoadState.loading);
    try {
      final status = await _repository.fetchStatus();
      setState(() {
        _status = status;
        _state = _LoadState.loaded;
      });
    } catch (e) {
      setState(() {
        _error = e is ApiException ? e : ApiException.network(e);
        _state = _LoadState.error;
      });
    }
  }

  Future<void> _connect() async {
    setState(() {
      _connecting = true;
      _connectError = null;
    });
    try {
      final authorization = await _repository.fetchAuthorization();
      final opened = await _launchUrl(
        Uri.parse(authorization.authorizationUrl),
      );
      if (!mounted) return;
      setState(() {
        _connecting = false;
        _connectError = opened
            ? null
            : "Couldn't open the Upstox sign-in page.";
      });
    } catch (e) {
      if (!mounted) return;
      final exception = e is ApiException ? e : ApiException.network(e);
      setState(() {
        _connecting = false;
        _connectError = exception.message;
      });
    }
  }

  String _formatDateTime(DateTime value) {
    final local = value.toLocal();
    final date =
        '${local.year}-${local.month.toString().padLeft(2, '0')}-${local.day.toString().padLeft(2, '0')}';
    final time =
        '${local.hour.toString().padLeft(2, '0')}:${local.minute.toString().padLeft(2, '0')}';
    return '$date $time';
  }

  @override
  Widget build(BuildContext context) {
    switch (_state) {
      case _LoadState.loading:
        return const MraCard(child: SkeletonCard());
      case _LoadState.error:
        return MraStateView.error(
          title: 'Upstox connection status unavailable',
          message: _error?.message,
          onAction: _load,
        );
      case _LoadState.loaded:
        return _buildLoaded(context, _status!);
    }
  }

  Widget _buildLoaded(BuildContext context, UpstoxStatus status) {
    final theme = Theme.of(context);
    final MraChipTone tone;
    final String label;
    if (status.connected) {
      tone = MraChipTone.positive;
      label = 'Connected';
    } else if (status.everConnected) {
      tone = MraChipTone.warning;
      label = 'Connection expired';
    } else {
      tone = MraChipTone.neutral;
      label = 'Not connected';
    }

    return MraCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text('Upstox', style: theme.textTheme.titleMedium),
              ),
              MraChip(label: label, tone: tone),
              const SizedBox(width: MraSpacing.xs),
              IconButton(
                tooltip: 'Refresh status',
                icon: const Icon(Icons.refresh),
                onPressed: _load,
              ),
            ],
          ),
          const SizedBox(height: MraSpacing.xs),
          Text(
            'Market data provider (${status.environment}). Trading/order '
            'execution is never enabled through this connection.',
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
          if (status.obtainedAt != null) ...[
            const SizedBox(height: MraSpacing.sm),
            Text(
              'Connected since ${_formatDateTime(status.obtainedAt!)}'
              '${status.expiresAt != null ? ' · expires ${_formatDateTime(status.expiresAt!)}' : ''}',
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ],
          if (!status.connected) ...[
            const SizedBox(height: MraSpacing.md),
            FilledButton.icon(
              icon: _connecting
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.link),
              label: Text(
                status.everConnected ? 'Reconnect Upstox' : 'Connect Upstox',
              ),
              onPressed: _connecting ? null : _connect,
            ),
            if (_connectError != null) ...[
              const SizedBox(height: MraSpacing.xs),
              Text(
                _connectError!,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.error,
                ),
              ),
            ],
          ],
        ],
      ),
    );
  }
}
