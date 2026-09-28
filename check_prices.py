import requests, time, re

time.sleep(0.5)

# Test games page
r = requests.get('http://127.0.0.1:5000/games', timeout=15)
print('/games page Status:', r.status_code)
count = r.text.lower().count('price not fetched yet')
prices = re.findall(r'class="fw-bold price-now"', r.text)
print('  "Price not fetched yet" count:', count)
print('  Price cards shown:', len(prices))

# Test home page
r2 = requests.get('http://127.0.0.1:5000/', timeout=15)
print('\n/ home page Status:', r2.status_code)
count2 = r2.text.lower().count('price not fetched yet')
prices2 = re.findall(r'class="fw-bold price-now"', r2.text)
print('  "Price not fetched yet" count:', count2)
print('  Price cards shown:', len(prices2))
