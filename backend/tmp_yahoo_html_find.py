import requests

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
}
url = 'https://finance.yahoo.com/quote/CL=F'
text = requests.get(url, headers=headers, timeout=20).text
print('text length', len(text))
print('CL=F count', text.count('CL=F'))
idx = -1
for i in range(20):
    idx = text.find('CL=F', idx + 1)
    if idx == -1:
        break
    print(i, idx)
    print(text[idx-100:idx+300])
    print('---')
