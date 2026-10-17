"""Double elimination: winners bracket, losers bracket, grand final with optional reset (FR-1.3).

Routing: WR1 losers pair up in LR1; WRr losers (r >= 2) drop into the away slot of
LR(2r-2); odd LB rounds feed the next even round 1:1 (home); even LB rounds halve
into the next odd round. WB final winner -> GF1.home, LB final winner -> GF1.away.
"""
from __future__ import annotations

from app.domain.fixtures import bracket as br
from app.domain.fixtures import validate as v


def generate(body: dict) -> dict:
    teams = v.teams(body, "double_elim")
    p = v.params(body)
    reset = v.opt_bool(p, "bracket_reset")
    results = br.parse_results(p)

    b = br.bracket_size(len(teams))
    k = b.bit_length() - 1
    wb = [[br.new_match(f"WR{r}M{i}", "winners", r, i) for i in range(1, b // 2 ** r + 1)]
          for r in range(1, k + 1)]
    lb = [[br.new_match(f"LR{r}M{i}", "losers", r, i) for i in range(1, b // 2 ** ((r + 1) // 2 + 1) + 1)]
          for r in range(1, 2 * (k - 1) + 1)]
    gf1 = br.new_match("GF1", "grand_final", 1, 1)
    gf = [gf1]
    if reset:
        gf2 = br.new_match("GF2", "grand_final", 2, 1)
        gf2.update(conditional=True, required=None)
        gf.append(gf2)
        gf1["winner_to"], gf1["loser_to"] = br.to("GF2", "home"), br.to("GF2", "away")

    for r, ms in enumerate(wb, start=1):
        for m in ms:
            i = m["index"]
            m["winner_to"] = (br.to(f"WR{r + 1}M{(i + 1) // 2}", "home" if i % 2 else "away") if r < k
                              else br.to("GF1", "home"))
            m["loser_to"] = (br.to(f"LR1M{(i + 1) // 2}", "home" if i % 2 else "away") if r == 1
                             else br.to(f"LR{2 * r - 2}M{i}", "away"))
    for r, ms in enumerate(lb, start=1):
        for m in ms:
            i = m["index"]
            if r == len(lb):
                m["winner_to"] = br.to("GF1", "away")
            elif r % 2 == 1:
                m["winner_to"] = br.to(f"LR{r + 1}M{i}", "home")
            else:
                m["winner_to"] = br.to(f"LR{r + 1}M{(i + 1) // 2}", "home" if i % 2 else "away")

    def on_decided(m: dict) -> None:
        if m["match_id"] == "GF1" and reset:
            lb_champ_won = m["winner"] == m["away"]
            gf[1]["required"] = lb_champ_won
            if lb_champ_won:  # keep GF2 positionally identical to GF1
                gf1["winner_to"], gf1["loser_to"] = br.to("GF2", "away"), br.to("GF2", "home")

    state: dict = {}
    br.seed_first_round(wb[0], teams, b, state)
    all_matches = [m for ms in wb for m in ms] + [m for ms in lb for m in ms] + gf
    br.resolve(all_matches, state, results, br.seeds_of(teams), on_decided)
    return {"format": "double_elim", "bracket_size": b, "bracket_reset": reset,
            "winners": [{"round": r, "matches": ms} for r, ms in enumerate(wb, start=1)],
            "losers": [{"round": r, "matches": ms} for r, ms in enumerate(lb, start=1)],
            "grand_final": gf}
