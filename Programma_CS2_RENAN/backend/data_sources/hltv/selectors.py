# Programma_CS2_RENAN/backend/data_sources/hltv/selectors.py


class HLTVURLBuilder:
    BASE_STATS_URL = "https://www.hltv.org/stats/players?csVersion=CS2"

    @staticmethod
    def build_url(time_filter="all", ranking="top30", event_type="BigEvents"):
        url = HLTVURLBuilder.BASE_STATS_URL
        if ranking == "top30":
            url += "&rankingFilter=Top30"
        if event_type == "BigEvents":
            url += "&matchType=BigEvents"
        # Add more as needed
        return url


class PlayerStatsSelectors:
    # From the main stats table
    TABLE_ROWS = ".stats-table tbody tr"
    NAME_COL = ".playerCol a"
    MAPS_COL = ".statsDetail"  # Usually maps played
    RATING_COL = ".ratingCol"

    # From the individual player profile stats
    PROFILE_STATS_ROWS = ".statistics .stat-row"
    STAT_LABEL = ".stat-label"
    STAT_VALUE = "span:last-child"
