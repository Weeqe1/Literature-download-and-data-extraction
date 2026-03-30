"""Quick test: 1 clause, all fixes applied."""
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

from etl_ensemble.harvester import LiteratureHarvester, load_config

cfg = load_config()
cfg["search"]["keywords"] = '("fluorescent nanoprobe")'
cfg["search"]["max_results_per_clause"] = 500
cfg["search"]["max_total"] = 5000
cfg["runtime"]["doi_fill_limit"] = 20

h = LiteratureHarvester(config=cfg)
h.run()
