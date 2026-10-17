import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/format.dart';
import '../../data/models.dart';
import '../../data/repository.dart';
import '../../widgets/async_view.dart';
import '../../widgets/tenant_title.dart';
import 'cart.dart';

class StoreScreen extends ConsumerStatefulWidget {
  const StoreScreen({super.key});

  @override
  ConsumerState<StoreScreen> createState() => _StoreScreenState();
}

class _StoreScreenState extends ConsumerState<StoreScreen> {
  String? _type; // null = all

  @override
  Widget build(BuildContext context) {
    final products = ref.watch(productsProvider);
    final cartCount = ref.watch(cartProvider).fold<int>(0, (n, l) => n + l.quantity);
    return Scaffold(
      appBar: AppBar(
        title: const TenantTitle('Store'),
        actions: [
          IconButton(
            tooltip: 'Cart, $cartCount items',
            onPressed: () => context.push('/cart'),
            icon: Badge(isLabelVisible: cartCount > 0, label: Text('$cartCount'), child: const Icon(Icons.shopping_cart)),
          ),
        ],
      ),
      body: AsyncView<List<Product>>(
        value: products,
        onRetry: () => ref.invalidate(productsProvider),
        isEmpty: (l) => l.isEmpty,
        emptyMessage: 'No products yet',
        builder: (all) {
          final list = _type == null ? all : all.where((p) => p.type == _type).toList();
          return RefreshIndicator(
            onRefresh: () => ref.refresh(productsProvider.future),
            child: ListView(padding: const EdgeInsets.all(8), children: [
              Wrap(spacing: 8, children: [
                for (final t in const [null, 'apparel', 'accessory', 'digital'])
                  ChoiceChip(
                    label: Text(t == null ? 'All' : humanize(t)),
                    selected: _type == t,
                    onSelected: (_) => setState(() => _type = t),
                  ),
              ]),
              if (list.isEmpty) const EmptyState(message: 'No products in this category'),
              for (final p in list)
                Card(
                  child: ListTile(
                    contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                    leading: const Icon(Icons.shopping_bag, size: 40, semanticLabel: 'Product'),
                    title: Text(p.name),
                    subtitle: Text('${humanize(p.type)} · from ${formatMoney(p.fromPriceMinor)}'),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => context.push('/product/${p.productId}'),
                  ),
                ),
            ]),
          );
        },
      ),
    );
  }
}
