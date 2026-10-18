import 'package:flutter/material.dart';

import '../core/format.dart';
import '../core/theme.dart';
import '../data/models.dart';
import 'async_view.dart';
import 'player_card.dart';
import 'ui.dart';

/// Staff tab: avatar, name, role.
class StaffList extends StatelessWidget {
  final Club club;
  const StaffList({super.key, required this.club});

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    if (club.staff.isEmpty) return const EmptyState(message: 'No staff listed', icon: Icons.badge_outlined);
    return Column(children: [
      for (var i = 0; i < club.staff.length; i++)
        Semantics(
          label: '${club.staff[i]['name']}, ${humanize('${club.staff[i]['role']}')}',
          excludeSemantics: true,
          child: Container(
            padding: const EdgeInsets.symmetric(vertical: 10),
            decoration: BoxDecoration(border: i == club.staff.length - 1 ? null : Border(bottom: BorderSide(color: p.hairline))),
            child: Row(children: [
              PlayerAvatar(name: '${club.staff[i]['name']}', clubId: club.clubId),
              const SizedBox(width: 12),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('${club.staff[i]['name']}', style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700, color: p.label)),
                  Text(humanize('${club.staff[i]['role']}'), style: TextStyle(fontSize: 13, color: p.label3)),
                ]),
              ),
            ]),
          ),
        ),
    ]);
  }
}

/// Venue tab: home ground panel, then the club's social accounts.
class VenueTab extends StatelessWidget {
  final Club club;
  const VenueTab({super.key, required this.club});

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      const SizedBox(height: 12),
      Semantics(
        label: 'Home venue ${club.venueName}${club.lat == null ? '' : ', coordinates ${club.lat}, ${club.lng}'}',
        excludeSemantics: true,
        child: Panel(
          padding: EdgeInsets.zero,
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            SizedBox(
              height: 120,
              child: Stack(fit: StackFit.expand, children: [
                PitchBackdrop(glow: p.accent),
                const Center(child: Icon(Icons.stadium_outlined, size: 48, color: Colors.white)),
              ]),
            ),
            Padding(
              padding: const EdgeInsets.all(16),
              child: Row(children: [
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(club.venueName.toUpperCase(), style: condensed(22, weight: FontWeight.w800, color: p.label)),
                    if (club.lat != null)
                      Text('${club.lat!.toStringAsFixed(4)}, ${club.lng!.toStringAsFixed(4)}',
                          style: TextStyle(fontSize: 13, color: p.label3, fontFeatures: tabular)),
                  ]),
                ),
                Icon(Icons.location_on_rounded, color: p.accent),
              ]),
            ),
          ]),
        ),
      ),
      if (club.socials.isNotEmpty) ...[
        const SectionLabel('Follow', padding: EdgeInsets.only(top: 20, bottom: 8)),
        for (final s in club.socials.entries) _SocialRow(platform: s.key, handle: '${s.value}'),
      ],
    ]);
  }
}

class _SocialRow extends StatelessWidget {
  final String platform;
  final String handle;
  const _SocialRow({required this.platform, required this.handle});

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    final (icon, label) = switch (platform.toLowerCase()) {
      'instagram' => (Icons.camera_alt_outlined, 'Instagram'),
      'x' || 'twitter' => (Icons.alternate_email_rounded, 'X'),
      'facebook' => (Icons.facebook_rounded, 'Facebook'),
      'youtube' => (Icons.smart_display_outlined, 'YouTube'),
      'tiktok' => (Icons.music_note_rounded, 'TikTok'),
      'website' || 'web' => (Icons.language_rounded, 'Website'),
      _ => (Icons.link_rounded, humanize(platform)),
    };
    return Semantics(
      label: '$label $handle',
      excludeSemantics: true,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 10),
        decoration: BoxDecoration(border: Border(bottom: BorderSide(color: p.hairline))),
        child: Row(children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(color: p.surface, borderRadius: BorderRadius.circular(10)),
            child: Icon(icon, color: p.accent, size: 20),
          ),
          const SizedBox(width: 12),
          Expanded(child: Text(handle, style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600, color: p.label))),
          Text(label.toUpperCase(), style: condensed(12, weight: FontWeight.w600, tracking: 1, color: p.label3)),
        ]),
      ),
    );
  }
}

/// History tab: one panel per season with W / D / L and a proportion bar.
class HistoryTab extends StatelessWidget {
  final Club club;
  const HistoryTab({super.key, required this.club});

  @override
  Widget build(BuildContext context) {
    if (club.stats.isEmpty) return const EmptyState(message: 'No past seasons yet', icon: Icons.history_rounded);
    return Column(children: [
      for (final s in club.stats) ...[
        const SizedBox(height: 12),
        SeasonPanel(
          season: '${s['season']}',
          played: (s['played'] as num?)?.toInt() ?? 0,
          won: (s['won'] as num?)?.toInt() ?? 0,
          drawn: (s['drawn'] as num?)?.toInt() ?? 0,
          lost: (s['lost'] as num?)?.toInt() ?? 0,
        ),
      ],
    ]);
  }
}

class SeasonPanel extends StatelessWidget {
  final String season;
  final int played, won, drawn, lost;
  const SeasonPanel({super.key, required this.season, required this.played, required this.won, required this.drawn, required this.lost});

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    final rate = played == 0 ? 0 : (won * 100 / played).round();
    final total = (won + drawn + lost) == 0 ? 1 : won + drawn + lost;
    Widget stat(String label, int v, Color c) => Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('$v', style: condensed(32, weight: FontWeight.w800, color: c, height: 1)),
            Text(label.toUpperCase(), style: condensed(12, weight: FontWeight.w600, tracking: 1, color: p.label3)),
          ]),
        );
    return Semantics(
      label: 'Season $season: $played played, $won won, $drawn drawn, $lost lost, $rate percent wins',
      excludeSemantics: true,
      child: Panel(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Text('SEASON $season', style: condensed(18, weight: FontWeight.w700, color: p.label)),
            const Spacer(),
            Text('$played played · $rate% wins', style: TextStyle(fontSize: 13, color: p.label3)),
          ]),
          const SizedBox(height: 12),
          Row(children: [stat('Won', won, p.accent), stat('Drawn', drawn, p.label), stat('Lost', lost, p.danger)]),
          const SizedBox(height: 12),
          ClipRRect(
            borderRadius: BorderRadius.circular(3),
            child: SizedBox(
              height: 6,
              child: Row(children: [
                if (won > 0) Expanded(flex: won * 100 ~/ total, child: ColoredBox(color: p.accent)),
                if (drawn > 0) Expanded(flex: drawn * 100 ~/ total, child: ColoredBox(color: p.label3)),
                if (lost > 0) Expanded(flex: lost * 100 ~/ total, child: ColoredBox(color: p.danger)),
              ]),
            ),
          ),
        ]),
      ),
    );
  }
}
