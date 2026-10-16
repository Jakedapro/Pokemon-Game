"""Entry point the PokeBrawl app is compiled from (tools/build_app.py)."""
import multiprocessing

from pokebrawl.__main__ import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
