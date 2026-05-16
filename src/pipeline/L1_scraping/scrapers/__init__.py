from src.pipeline.L1_scraping.scrapers import (
    rss, moneycontrol, economic_times,
    newsdata, mediastack, gmail, youtube,
    india_macro, us_macro, fii_dii, bulk_deals, fno,
)

SCRAPERS = {
    "rss":            rss.collect,
    "moneycontrol":   moneycontrol.collect,
    "economic_times": economic_times.collect,
    "newsdata_io":    newsdata.collect,
    "mediastack":     mediastack.collect,
    "gmail":          gmail.collect,
    "youtube":        youtube.collect,
    "india_macro":    india_macro.collect,
    "us_macro":       us_macro.collect,
    "fii_dii":        fii_dii.collect,
    "bulk_deals":     bulk_deals.collect,
    "fno":            fno.collect,
}
