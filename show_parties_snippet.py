import pathlib
text = pathlib.Path('index.packed.js').read_text()
idx = text.find('"parties"')
print(idx)
print(text[idx-200:idx+200])
