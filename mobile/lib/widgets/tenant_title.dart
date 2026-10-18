import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/format.dart';
import '../core/session.dart';
import '../core/theme.dart';
import 'team_crest.dart';

/// The tenant's mark (white-label). Logo when available, else a crest in the tenant colour.
class TenantMark extends ConsumerWidget {
  final double size;
  const TenantMark({super.key, this.size = 34});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final tenant = ref.watch(sessionProvider)?.tenant;
    final p = context.palette;
    final crest = CrestShape(
      initials: initialsOf(tenant?.name ?? 'NaSCon Sports'),
      primary: p.accent,
      secondary: p.accentDeep,
      textColor: p.onAccent,
      size: size,
    );
    return Semantics(
      label: '${tenant?.name ?? 'App'} logo',
      image: true,
      excludeSemantics: true,
      child: tenant?.logoUrl == null
          ? crest
          : ClipRRect(
              borderRadius: crestRadius(size, size * 1.12),
              child: Image.network(
                tenant!.logoUrl!,
                width: size,
                height: size * 1.12,
                fit: BoxFit.cover,
                errorBuilder: (_, _, _) => crest,
              ),
            ),
    );
  }
}
