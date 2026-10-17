import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/session.dart';
import '../core/theme.dart';

/// The tenant's mark (white-label). Logo when available, else a monogram on the accent colour.
/// Shown once per surface (branding.md: logos don't repeat), not in every app bar.
class TenantMark extends ConsumerWidget {
  final double size;
  const TenantMark({super.key, this.size = 32});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final tenant = ref.watch(sessionProvider)?.tenant;
    final p = context.palette;
    final initials = (tenant?.name ?? 'N')
        .split(' ')
        .where((w) => w.isNotEmpty)
        .take(2)
        .map((w) => w[0].toUpperCase())
        .join();
    final monogram = Container(
      width: size,
      height: size,
      alignment: Alignment.center,
      decoration: BoxDecoration(color: p.accent, borderRadius: BorderRadius.circular(size * 0.28)),
      child: Text(
        initials,
        style: TextStyle(color: Colors.white, fontWeight: FontWeight.w700, fontSize: size * 0.38),
      ),
    );
    return Semantics(
      label: '${tenant?.name ?? 'App'} logo',
      image: true,
      excludeSemantics: true,
      child: tenant?.logoUrl == null
          ? monogram
          : ClipRRect(
              borderRadius: BorderRadius.circular(size * 0.28),
              child: Image.network(tenant!.logoUrl!, width: size, height: size, errorBuilder: (_, _, _) => monogram),
            ),
    );
  }
}
