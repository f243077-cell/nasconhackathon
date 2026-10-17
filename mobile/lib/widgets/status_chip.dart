import 'package:flutter/material.dart';

import '../core/format.dart';

/// Colour + icon + TEXT, so meaning never depends on colour alone.
class StatusChip extends StatelessWidget {
  final String label;
  final IconData icon;
  final Color color;
  const StatusChip({super.key, required this.label, required this.icon, required this.color});

  factory StatusChip.match(String status) => switch (status) {
        'in_progress' => const StatusChip(label: 'Live', icon: Icons.circle, color: Colors.red),
        'completed' => const StatusChip(label: 'Full time', icon: Icons.check_circle, color: Colors.grey),
        'upcoming' => const StatusChip(label: 'Upcoming', icon: Icons.schedule, color: Colors.blue),
        'postponed' => const StatusChip(label: 'Postponed', icon: Icons.update, color: Colors.orange),
        _ => StatusChip(label: humanize(status), icon: Icons.info_outline, color: Colors.grey),
      };

  factory StatusChip.qualification(String status) => switch (status) {
        'clinched' => const StatusChip(label: 'Clinched', icon: Icons.verified, color: Colors.green),
        'eliminated' => const StatusChip(label: 'Eliminated', icon: Icons.cancel, color: Colors.red),
        _ => const StatusChip(label: 'Still possible', icon: Icons.more_horiz, color: Colors.orange),
      };

  factory StatusChip.sync(String status) => switch (status) {
        'applied' => const StatusChip(label: 'Applied', icon: Icons.check_circle, color: Colors.green),
        'duplicate' => const StatusChip(label: 'Already synced', icon: Icons.copy, color: Colors.grey),
        'rejected' => const StatusChip(label: 'Rejected', icon: Icons.block, color: Colors.red),
        _ => const StatusChip(label: 'Pending', icon: Icons.schedule, color: Colors.orange),
      };

  @override
  Widget build(BuildContext context) => Chip(
        avatar: Icon(icon, size: 16, color: color),
        label: Text(label),
        visualDensity: VisualDensity.compact,
        side: BorderSide(color: color),
      );
}
