from services.price_fetcher import PriceFetcher
prices = PriceFetcher.fetch_all_prices()
print(sorted(prices.keys()))
for s in ['WTI','Brent','RBOB','HO','GO','HH','DUBAICRUDE','WCS-WTI']:
    print(s, prices.get(s))
