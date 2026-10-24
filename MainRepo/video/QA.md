# Q&A cheat sheet (6 minutes with AEP engineers)

- **Where does "6 to 14 hours" come from?** Real labor hours per damage type from AEP's workbook, ×4.5 for travel and setup, crews from a regional pool of 150 (calibrated so replayed repair times match real Feb 2025 ARCOS: 38/38/16/7% fixed in 0/1/2/3+ days vs 39/33/18/10% real), 1,000 Monte Carlo runs, P10 to P90.
- **Is the outage map real?** The damage and the network are real. The live feed is simulated: we replay Feb 2025 damage on a clock and trace each damaged device through the real upstream map to the homes it knocks out. AEP's real outage feed would plug into the same slot.
- **Why did the estimate change?** It only knows damage reported so far. When a second damaged spot on Maya's path was reported, the range moved, as it would in real life.
- **How good is the risk band?** It's relative, built only from storms before the replayed one. Backtest: the High band held about 2.5× its share of later damage. One region, few storms; we say so.
- **What does "switching" do?** It's the network assumption. With switching, only repairs on your own path matter. Without it, you wait for every repair on your line.
- **Privacy?** Hashed ids, ~1 km cells with 10+ homes, no addresses, no crew info, no life-support data used, needs are never stored, audit log has no personal content.
- **What if the AI makes something up?** Numbers come only from our tools; a number check rejects any reply with a number not in the tool output; safety text is fixed; it works without the LLM too.
- **What would you need next?** AEP's live outage/AMI feed, weather forecasts, real restoration-time history, more regions and storms.
