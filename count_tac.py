import pathlib
text = pathlib.Path('index.packed.js').read_text()
count = text.count('"tac"')
print('count', count)
