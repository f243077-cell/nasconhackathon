import 'package:flutter/material.dart';

/// The PlayGrid app mark (lime "P" with a play cut-out on the night canvas).
/// Tenants keep their own mark (TenantMark); this is the product's brand.
class AppLogo extends StatelessWidget {
  final double size;
  const AppLogo({super.key, this.size = 40});

  @override
  Widget build(BuildContext context) => Semantics(
        label: 'PlayGrid logo',
        image: true,
        excludeSemantics: true,
        child: ClipRRect(
          borderRadius: BorderRadius.circular(size * 0.24),
          child: Image.asset('assets/brand/logo.png', width: size, height: size, fit: BoxFit.cover),
        ),
      );
}
