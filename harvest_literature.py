"""Harvester entry point - delegates to etl_ensemble.harvester."""
import logging
from logging_config import setup_logging
from etl_ensemble.harvester import LiteratureHarvester, load_config


def main():
    setup_logging()
    cfg = load_config()
    harvester = LiteratureHarvester(config=cfg)
    harvester.run()


if __name__ == "__main__":
    main()
