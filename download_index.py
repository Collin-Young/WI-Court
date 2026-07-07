import httpx
text = httpx.get('https://wcca.wicourts.gov/versionedResource/17131b23222/js/index.packed.js').text
open('index.packed.js','w', encoding='utf-8').write(text)
print('done', len(text))
