import 'package:flutter_test/flutter_test.dart';
import 'package:mra_app/features/tracking/tracking_filters.dart';

void main() {
  test('default TrackingFilters is empty with zero active count', () {
    const filters = TrackingFilters();
    expect(filters.isEmpty, true);
    expect(filters.activeCount, 0);
    expect(filters.toQuery(), isEmpty);
  });

  test('toQuery only includes set fields', () {
    const filters = TrackingFilters(horizon: 5, symbol: 'AAA');
    final query = filters.toQuery();
    expect(query, {'horizon': '5', 'symbol': 'AAA'});
  });

  test('a from/to pair counts as a single active filter dimension', () {
    final filters = TrackingFilters(
      from: DateTime.utc(2026, 1, 1),
      to: DateTime.utc(2026, 1, 31),
    );
    expect(filters.activeCount, 1);
    expect(filters.isEmpty, false);
  });

  test('activeCount counts every set dimension', () {
    const filters = TrackingFilters(
      horizon: 3,
      sector: 'TECH',
      marketCap: 'LARGE_CAP',
      regime: 'BULLISH_LOW_VOL',
      symbol: 'AAA',
    );
    expect(filters.activeCount, 5);
  });

  test('copyWith sets a field without disturbing others', () {
    const base = TrackingFilters(sector: 'TECH');
    final updated = base.copyWith(horizon: 5);
    expect(updated.sector, 'TECH');
    expect(updated.horizon, 5);
  });

  test('copyWith clear flags remove a field', () {
    const base = TrackingFilters(horizon: 5, sector: 'TECH');
    final cleared = base.copyWith(clearHorizon: true);
    expect(cleared.horizon, null);
    expect(cleared.sector, 'TECH');
  });

  test('copyWith clearRange removes both from and to together', () {
    final base = TrackingFilters(
      from: DateTime.utc(2026, 1, 1),
      to: DateTime.utc(2026, 1, 31),
    );
    final cleared = base.copyWith(clearRange: true);
    expect(cleared.from, null);
    expect(cleared.to, null);
  });
}
