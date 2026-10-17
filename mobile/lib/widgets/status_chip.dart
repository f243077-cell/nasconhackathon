import 'package:flutter/material.dart';

import '../core/format.dart';
import '../core/theme.dart';

enum _Tone { live, success, warning, danger, neutral, accent }

/// Small tinted capsule: icon + TEXT + colour, so meaning never depends on colour alone.
class StatusChip extends StatelessWidget {
  final String label;
  final IconData icon;
  final _Tone _tone;

  const StatusChip._(this.label, this.icon, this._tone);

  factory StatusChip.match(String status) => switch (status) {
        'in_progress' => const StatusChip._('Live', Icons.circle, _Tone.live),
        'completed' => const StatusChip._('Full Time', Icons.check_rounded, _Tone.neutral),
        'upcoming' => const StatusChip._('Upcoming', Icons.schedule_rounded, _Tone.accent),
        'postponed' => const StatusChip._('Postponed', Icons.update_rounded, _Tone.warning),
        _ => StatusChip._(humanize(status), Icons.info_outline_rounded, _Tone.neutral),
      };

  factory StatusChip.qualification(String status) => switch (status) {
        'clinched' => const StatusChip._('Clinched', Icons.check_circle_rounded, _Tone.success),
        'eliminated' => const StatusChip._('Eliminated', Icons.cancel_rounded, _Tone.danger),
        _ => const StatusChip._('In Contention', Icons.remove_circle_outline_rounded, _Tone.warning),
      };

  factory StatusChip.sync(String status) => switch (status) {
        'applied' => const StatusChip._('Applied', Icons.check_circle_rounded, _Tone.success),
        'duplicate' => const StatusChip._('Already Synced', Icons.done_all_rounded, _Tone.neutral),
        'rejected' => const StatusChip._('Rejected', Icons.block_rounded, _Tone.danger),
        _ => const StatusChip._('Pending', Icons.schedule_rounded, _Tone.warning),
      };

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    final color = switch (_tone) {
      _Tone.live => p.live,
      _Tone.success => p.success,
      _Tone.warning => p.warning,
      _Tone.danger => p.danger,
      _Tone.accent => p.accent,
      _Tone.neutral => p.secondaryLabel,
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
      decoration: BoxDecoration(color: color.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(100)),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(icon, size: _tone == _Tone.live ? 8 : 14, color: color),
        const SizedBox(width: 5),
        Text(label, style: Theme.of(context).textTheme.labelMedium!.copyWith(color: color)),
      ]),
    );
  }
}
