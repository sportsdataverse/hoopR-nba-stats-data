"""Reshaper for the ``hoopR-nba-stats-raw`` store into published ``nba_stats_*`` datasets.

A port of the proven WNBA reshaper (``wehoop-wnba-stats-data``), adapted for NBA's
two-calendar-year season convention (start-year labels; game endpoints keyed by the
season *end* year) and the ``hoopR_data`` release stamp. Reads only committed raw
payloads, so a build makes no network calls and is reproducible from a checkout.
"""
