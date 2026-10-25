"""Pick the 3 demo homes and write data/demo_homes.json (committed).

    python -m ingest.find_story_home

Rerun after rebuilding the DB with a different CONCIERGE_SALT (home ids change with the salt).
"""
from app.sim.story import DEMO_HOMES, write

if __name__ == "__main__":
    homes = write()
    print(f"wrote {DEMO_HOMES}")
    for k in ("story", "second", "fallback"):
        print(f"  {k}: {homes[k]}")
