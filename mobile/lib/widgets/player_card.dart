import 'package:flutter/material.dart';

import '../core/format.dart';
import '../core/theme.dart';
import '../data/models.dart';
import 'team_crest.dart';
import 'ui.dart';

const playerPositions = {'GK': 'Goalkeeper', 'DF': 'Defender', 'MF': 'Midfielder', 'FW': 'Forward'};

/// Round player photo (`assets/players/<player_id>.png`), else initials on the club colour.
class PlayerAvatar extends StatelessWidget {
  final String? playerId;
  final String name;
  final String? clubId;
  final double size;
  const PlayerAvatar({super.key, this.playerId, required this.name, this.clubId, this.size = 40});

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    final initials = Container(
      width: size,
      height: size,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: clubId == null ? p.raised : Color.lerp(TeamCrest.colorFor(clubId!), p.canvas, 0.25),
      ),
      child: Text(initialsOf(name), style: condensed(size * 0.4, weight: FontWeight.w800, color: Colors.white)),
    );
    return ExcludeSemantics(
      child: ClipOval(
        child: playerId == null
            ? initials
            : Image.asset('assets/players/$playerId.png', width: size, height: size, fit: BoxFit.cover, errorBuilder: (_, _, _) => initials),
      ),
    );
  }
}

/// One squad member: photo, position code, name, "Position · role" (or loan / sync state), C / VC badge.
class SquadRow extends StatelessWidget {
  final RosterPlayer player;
  final String clubId;
  final bool waitingToSync;
  final bool dense;
  final bool divider;
  final VoidCallback? onTap;
  const SquadRow({
    super.key,
    required this.player,
    required this.clubId,
    this.waitingToSync = false,
    this.dense = false,
    this.divider = true,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    final position = playerPositions[player.position] ?? player.position;
    final badge = switch (player.role) {
      'captain' => Tag('C', color: p.accent, textColor: p.onAccent, fontSize: 12),
      'vice_captain' => Tag('VC', color: p.label3, outlined: true, textColor: p.label, fontSize: 12),
      _ => null,
    };
    final (detail, detailColor) = waitingToSync
        ? ('⟳ Waiting to sync', p.warning)
        : player.onLoan
            ? ('On loan · $position', p.warning)
            : ([position, if (player.role != 'player' && player.role != 'substitute' || badge != null) humanize(player.role)].join(' · '), p.label3);

    return Semantics(
      button: onTap != null,
      label: '${player.name}, $detail',
      excludeSemantics: true,
      child: InkWell(
        onTap: onTap,
        child: Container(
          padding: EdgeInsets.symmetric(vertical: dense ? 8 : 10),
          decoration: BoxDecoration(border: divider ? Border(bottom: BorderSide(color: p.hairline)) : null),
          child: Row(children: [
            if (!dense) ...[PlayerAvatar(playerId: player.playerId, name: player.name, clubId: clubId), const SizedBox(width: 12)],
            SizedBox(
              width: 30,
              child: Text(player.position, style: condensed(dense ? 16 : 18, weight: FontWeight.w800, color: p.muted)),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(player.name, maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700, color: p.label)),
                if (!dense) Text(detail, maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 13, color: detailColor)),
              ]),
            ),
            ?badge,
          ]),
        ),
      ),
    );
  }
}
