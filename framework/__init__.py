"""Framework package for BT396.

Holds the single source of truth for the package version and release date.
Update __version__ and __release_date__ when making a release.
"""

__all__ = ["__version__", "__release_date__"]

# Semantic version of the BT396 project
__version__ = "0.1.5"
# Release date (YYYY-MM-DD)
__release_date__ = "2026-10-05"

# Change history
# 0.1.0 - 2025-06-20 - Initial release
# 0.1.1 - 2025-10-04 - improved graph labelling (unreleased)
# 0.1.2 - 2025-10-29 - added True PD Ratio, date range, improved graph labelling (unreleased)
# 0.1.3 - 2025-11-04 - improved comments (released)
# 0.1.4 - 2026-10-01 - Simplified PD ratio (just the one metric)
#			corrected bugs:
#			fixed possible unclosed positions on liquidation due to series ends not syncing.
#			PD ratio now displaying actual loss when negative and PD ratio when profitable, as per the 
#			 lecture slides.
# 			Tidied plots and plot axes labelled correctly. 
#			Added 2026-27 data series part1.
# 0.1.5 - 2026-10-04 - bugs fixed, example strategies polished.