import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/errors.dart';
import '../core/theme.dart';

class LoadingView extends StatelessWidget {
  final String label;
  const LoadingView({super.key, this.label = 'Loading'});

  @override
  Widget build(BuildContext context) => Center(
        child: Semantics(
          label: label,
          liveRegion: true,
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            const CupertinoActivityIndicator(radius: 13),
            const SizedBox(height: 12),
            Text(label, style: Theme.of(context).textTheme.bodyMedium),
          ]),
        ),
      );
}

/// Quiet empty state: one muted symbol, a sentence, optional next action.
class EmptyState extends StatelessWidget {
  final String message;
  final IconData icon;
  final Widget? action;
  const EmptyState({super.key, required this.message, this.icon = Icons.inbox_rounded, this.action});

  @override
  Widget build(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 48),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Icon(icon, size: 44, color: context.palette.secondaryLabel, semanticLabel: message),
            const SizedBox(height: 14),
            Text(message, textAlign: TextAlign.center, style: Theme.of(context).textTheme.titleMedium),
            if (action != null) ...[const SizedBox(height: 20), action!],
          ]),
        ),
      );
}

class ErrorView extends StatelessWidget {
  final String message;
  final VoidCallback? onRetry;
  const ErrorView({super.key, required this.message, this.onRetry});

  @override
  Widget build(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 48),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Icon(Icons.wifi_off_rounded, size: 44, color: context.palette.secondaryLabel, semanticLabel: 'Problem'),
            const SizedBox(height: 14),
            Text(message, textAlign: TextAlign.center, style: Theme.of(context).textTheme.titleMedium),
            if (onRetry != null) ...[
              const SizedBox(height: 16),
              TextButton(onPressed: onRetry, child: const Text('Try Again')),
            ],
          ]),
        ),
      );
}

/// Loading / empty / error / data for any AsyncValue, cross-fading between states.
class AsyncView<T> extends StatelessWidget {
  final AsyncValue<T> value;
  final Widget Function(T data) builder;
  final bool Function(T data)? isEmpty;
  final String emptyMessage;
  final VoidCallback? onRetry;

  const AsyncView({
    super.key,
    required this.value,
    required this.builder,
    this.isEmpty,
    this.emptyMessage = 'Nothing here yet',
    this.onRetry,
  });

  @override
  Widget build(BuildContext context) {
    final reduce = MediaQuery.of(context).disableAnimations;
    final (key, child) = value.when(
      loading: () => ('loading', const LoadingView()),
      error: (e, _) => ('error', ErrorView(message: friendlyError(e), onRetry: onRetry)),
      data: (data) => (isEmpty?.call(data) ?? false)
          ? ('empty', EmptyState(message: emptyMessage))
          : ('data', builder(data)),
    );
    return AnimatedSwitcher(
      duration: reduce ? Duration.zero : const Duration(milliseconds: 220),
      switchInCurve: Curves.easeOut,
      child: KeyedSubtree(key: ValueKey(key), child: child),
    );
  }
}

/// Same as [AsyncView] but for CustomScrollView pages: [builder] returns a sliver.
class AsyncSliver<T> extends StatelessWidget {
  final AsyncValue<T> value;
  final Widget Function(T data) builder;
  final bool Function(T data)? isEmpty;
  final String emptyMessage;
  final IconData emptyIcon;
  final VoidCallback? onRetry;

  const AsyncSliver({
    super.key,
    required this.value,
    required this.builder,
    this.isEmpty,
    this.emptyMessage = 'Nothing here yet',
    this.emptyIcon = Icons.inbox_rounded,
    this.onRetry,
  });

  @override
  Widget build(BuildContext context) {
    Widget fill(Widget child) => SliverFillRemaining(hasScrollBody: false, child: child);
    return value.when(
      loading: () => fill(const LoadingView()),
      error: (e, _) => fill(ErrorView(message: friendlyError(e), onRetry: onRetry)),
      data: (data) =>
          (isEmpty?.call(data) ?? false) ? fill(EmptyState(message: emptyMessage, icon: emptyIcon)) : builder(data),
    );
  }
}

void showSuccess(BuildContext context, String message) => ScaffoldMessenger.of(context)
  ..hideCurrentSnackBar()
  ..showSnackBar(SnackBar(content: Text(message)));

void showError(BuildContext context, Object error) => ScaffoldMessenger.of(context)
  ..hideCurrentSnackBar()
  ..showSnackBar(SnackBar(
    content: Row(children: [
      Icon(Icons.error_rounded, color: context.palette.danger, size: 20, semanticLabel: 'Error'),
      const SizedBox(width: 10),
      Expanded(child: Text(friendlyError(error))),
    ]),
  ));
