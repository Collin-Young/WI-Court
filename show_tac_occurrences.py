import pathlib
text = pathlib.Path('index.packed.js').read_text()
start = 0
for _ in range(5):
    idx = text.find('"tac"', start)
    print(idx)
    print(text[idx-200:idx+200])
    print('---')
    start = idx + 5
