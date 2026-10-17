"""Single elimination with exact seeding, byes and an optional third-place match (FR-1.3)."""
from __future__ import annotations

from app.domain.fixtures import bracket as br
from app.domain.fixtures import validate as v


def generate(body: dict) -> dict:
    teams = v.teams(body, "single_elim")
    p = v.params(body)
    third = v.opt_bool(p, "third_place_match")
    results = br.parse_results(p)

    b = br.bracket_size(len(teams))
    rounds_n = b.bit_length() - 1
    rounds = [[br.new_match(f"R{r}M{i}", "main", r, i) for i in range(1, b // 2 ** r + 1)]
              for r in range(1, rounds_n + 1)]
    for r, ms in enumerate(rounds, start=1):
        if r < rounds_n:
            for m in ms:
                i = m["index"]
                m["winner_to"] = br.to(f"R{r + 1}M{(i + 1) // 2}", "home" if i % 2 else "away")
    if third and rounds_n >= 2:
        for m in rounds[-2]:
            m["loser_to"] = br.to("TP", "home" if m["index"] == 1 else "away")
        rounds[-1].append(br.new_match("TP", "third_place", rounds_n, 1))

    state: dict = {}
    br.seed_first_round(rounds[0], teams, b, state)
    br.resolve([m for ms in rounds for m in ms], state, results, br.seeds_of(teams))
    return {"format": "single_elim", "bracket_size": b,
            "rounds": [{"round": r, "matches": ms} for r, ms in enumerate(rounds, start=1)]}
