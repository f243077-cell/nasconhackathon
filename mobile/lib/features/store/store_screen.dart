import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/format.dart';
import '../../core/theme.dart';
import '../../data/models.dart';
import '../../data/repository.dart';
import '../../widgets/async_view.dart';
import '../../widgets/ui.dart';
import 'cart.dart';

class StoreScreen extends ConsumerStatefulWidget {
  const StoreScreen({super.key});

  @override
  ConsumerState<StoreScreen> createState() => _StoreScreenState();
}

class _StoreScreenState extends ConsumerState<StoreScreen> {
  String _type = 'all';

  @override
  Widget build(BuildContext context) {
    final products = ref.watch(productsProvider);
    final cartCount = ref.watch(cartProvider).fold<int>(0, (n, l) => n + l.quantity);
    return TabPage(
      title: 'Store',
      kicker: 'Official club merch',
      headerTrailing: CartButton(count: cartCount),
      onRefresh: () => ref.refresh(productsProvider.future),
      slivers: [
        SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.only(bottom: 16),
            child: PillChips<String>(
              value: _type,
              options: const {'all': 'All', 'apparel': 'Apparel', 'accessory': 'Gear', 'digital': 'Digital'},
              onChanged: (v) => setState(() => _type = v),
            ),
          ),
        ),
        AsyncSliver<List<Product>>(
          value: products,
          onRetry: () => ref.invalidate(productsProvider),
          isEmpty: (all) => (_type == 'all' ? all : all.where((p) => p.type == _type)).isEmpty,
          emptyMessage: _type == 'all' ? 'No products yet' : 'Nothing in this category yet',
          emptyIcon: Icons.shopping_bag_outlined,
          builder: (all) {
            final list = _type == 'all' ? all : all.where((p) => p.type == _type).toList();
            return SliverGrid.builder(
              gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
                maxCrossAxisExtent: 220,
                mainAxisSpacing: 16,
                crossAxisSpacing: 12,
                mainAxisExtent: 230,
              ),
              itemCount: list.length,
              itemBuilder: (_, i) => _ProductTile(product: list[i]),
            );
          },
        ),
      ],
    );
  }
}

/// Round cart button with the item count badge.
class CartButton extends StatelessWidget {
  final int count;
  const CartButton({super.key, required this.count});

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    return Semantics(
      button: true,
      label: count == 0 ? 'Cart' : 'Cart, $count items',
      excludeSemantics: true,
      child: GestureDetector(
        onTap: () => context.push('/cart'),
        child: SizedBox(
          width: 48,
          height: 48,
          child: Stack(clipBehavior: Clip.none, alignment: Alignment.center, children: [
            Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(color: p.surface, shape: BoxShape.circle),
              child: Icon(Icons.shopping_bag_outlined, size: 22, color: p.label),
            ),
            if (count > 0)
              Positioned(
                top: 0,
                right: 0,
                child: Container(
                  constraints: const BoxConstraints(minWidth: 20),
                  height: 20,
                  padding: const EdgeInsets.symmetric(horizontal: 5),
                  alignment: Alignment.center,
                  decoration: BoxDecoration(color: p.accent, borderRadius: BorderRadius.circular(10)),
                  child: Text('$count', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: p.onAccent)),
                ),
              ),
          ]),
        ),
      ),
    );
  }
}

/// Image, stock badge, name, price. The tile is the button; no card chrome around it.
class _ProductTile extends StatelessWidget {
  final Product product;
  const _ProductTile({required this.product});

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    final inStock = product.variants.where((v) => v.stock > 0);
    final soldOut = inStock.isEmpty;
    final lowest = inStock.isEmpty ? 0 : inStock.map((v) => v.stock).reduce((a, b) => a < b ? a : b);
    final samePrice = product.variants.map((v) => v.priceMinor).toSet().length <= 1;
    final badge = soldOut
        ? Tag('Sold out', color: p.label)
        : product.type == 'digital'
            ? Tag('Digital', color: p.label)
            : (lowest <= 3 ? Tag('$lowest left', color: p.warning) : null);
    final price = soldOut ? 'Sold out' : '${samePrice ? '' : 'From '}${formatMoney(product.fromPriceMinor)}';

    return Semantics(
      button: true,
      label: '${product.name}, $price${!soldOut && badge != null && product.type != 'digital' ? ', only $lowest left' : ''}',
      excludeSemantics: true,
      child: GestureDetector(
        onTap: () => context.push('/product/${product.productId}'),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Expanded(
            child: Stack(children: [
              Positioned.fill(
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(14),
                  child: Opacity(
                    opacity: soldOut ? 0.5 : 1,
                    child: ProductArtwork(type: product.type, imageUrl: product.imageUrl),
                  ),
                ),
              ),
              if (badge != null) Positioned(left: 8, top: 8, child: badge),
            ]),
          ),
          const SizedBox(height: 8),
          Text(product.name, maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600, color: p.label)),
          Text(price, style: condensed(17, weight: FontWeight.w700, color: soldOut ? p.label3 : p.accent)),
        ]),
      ),
    );
  }
}
