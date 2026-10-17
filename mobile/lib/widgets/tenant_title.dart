import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/session.dart';

/// App bar title with the tenant logo (white-label). Falls back to an icon offline / no logo.
class TenantTitle extends ConsumerWidget {
  final String title;
  const TenantTitle(this.title, {super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final logo = ref.watch(sessionProvider)?.tenant.logoUrl;
    const fallback = Icon(Icons.sports_soccer, semanticLabel: 'Logo');
    return Row(children: [
      if (logo == null)
        fallback
      else
        Image.network(logo, height: 28, width: 28, semanticLabel: 'Logo', errorBuilder: (_, _, _) => fallback),
      const SizedBox(width: 12),
      Flexible(child: Text(title, overflow: TextOverflow.ellipsis)),
    ]);
  }
}
