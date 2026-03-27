import secrets
from osbot_utils.type_safe.Type_Safe             import Type_Safe
from sgit_ai.safe_types.Safe_Str__Simple_Token   import Safe_Str__Simple_Token

WORDLIST = [
    'able', 'acid', 'aged', 'also', 'area', 'army', 'atom', 'aunt',
    'back', 'ball', 'band', 'bank', 'bare', 'barn', 'base', 'bath',
    'bead', 'beam', 'bear', 'beat', 'beef', 'bell', 'belt', 'bend',
    'bike', 'bill', 'bind', 'bird', 'bite', 'blow', 'blue', 'boat',
    'bold', 'bolt', 'bond', 'bone', 'book', 'boot', 'bore', 'born',
    'boss', 'both', 'bowl', 'brow', 'bulk', 'burn', 'busy',
    'cafe', 'cage', 'cake', 'calm', 'came', 'camp', 'card', 'care',
    'cart', 'case', 'cash', 'cast', 'cave', 'cell', 'chat', 'chip',
    'city', 'clam', 'clay', 'clip', 'club', 'coal', 'coat', 'code',
    'coil', 'coin', 'cold', 'cone', 'cook', 'cool', 'cope', 'copy',
    'cord', 'core', 'cork', 'corn', 'cost', 'coup', 'crew', 'crop',
    'cure', 'curl', 'cute',
    'damp', 'dare', 'dark', 'dart', 'data', 'dawn', 'dead', 'dear',
    'debt', 'deck', 'deed', 'deep', 'deer', 'deft', 'dent', 'desk',
    'dial', 'dice', 'diet', 'disc', 'dish', 'disk', 'dive', 'dock',
    'does', 'dome', 'door', 'dose', 'down', 'draw', 'drew', 'drip',
    'drop', 'drum', 'dusk', 'dust', 'duty',
    'earl', 'earn', 'ease', 'east', 'edge', 'emit', 'even', 'ever',
    'evil', 'exam',
    'face', 'fact', 'fade', 'fail', 'fair', 'fall', 'fame', 'farm',
    'fast', 'fate', 'feel', 'felt', 'fern', 'file', 'fill', 'film',
    'find', 'fine', 'fire', 'firm', 'fish', 'fist', 'flag', 'flat',
    'flew', 'flip', 'flow', 'foam', 'foil', 'fold', 'folk', 'fond',
    'font', 'food', 'fool', 'foot', 'ford', 'fore', 'fork', 'form',
    'fort', 'foul', 'four', 'free', 'from', 'fuel', 'full', 'fuse',
    'gain', 'gale', 'gaze', 'gear', 'gene', 'gild', 'give', 'glad',
    'glen', 'glow', 'glue', 'goal', 'gold', 'golf', 'gown', 'grab',
    'gram', 'grew', 'grid', 'grin', 'grip', 'grow', 'gulf', 'gust',
    'hail', 'half', 'hall', 'halt', 'hand', 'hang', 'hard', 'harm',
    'harp', 'hash', 'haze', 'head', 'heal', 'heap', 'heat', 'heel',
    'held', 'helm', 'help', 'herb', 'herd', 'hero', 'hike', 'hill',
    'hint', 'hire', 'hold', 'hole', 'home', 'hood', 'hook', 'hope',
    'horn', 'hose', 'host', 'hour', 'huge', 'hull', 'hump', 'hunt',
    'hurt',
    'idea', 'idle', 'inch', 'iron', 'isle', 'item',
    'jack', 'jade', 'jail', 'join', 'joke', 'jump', 'just',
    'keen', 'keep', 'kern', 'kind', 'king', 'knot',
    'lack', 'lake', 'lamp', 'land', 'lane', 'lark', 'last', 'laud',
    'lawn', 'lead', 'leaf', 'lean', 'leap', 'left', 'lend', 'lens',
    'life', 'lift', 'lime', 'line', 'link', 'lint', 'lion', 'list',
    'load', 'loan', 'lobe', 'lock', 'loft', 'logo', 'long', 'loom',
    'loop', 'lore', 'lorn', 'loss', 'lost', 'loud', 'lump', 'lung',
    'lure', 'lurk', 'lute',
    'made', 'mail', 'main', 'make', 'mall', 'malt', 'mane', 'mare',
    'mark', 'mart', 'mask', 'mast', 'mate', 'math', 'maze', 'mead',
    'meal', 'meat', 'melt', 'memo', 'menu', 'mesh', 'mild', 'milk',
    'mill', 'mime', 'mind', 'mine', 'mint', 'miss', 'mist', 'mode',
    'mole', 'monk', 'moon', 'moor', 'more', 'moss', 'most', 'mote',
    'move', 'much', 'mule', 'myth',
]


class Simple_Token__Wordlist(Type_Safe):
    words : list

    def setup(self):
        if not self.words:
            self.words = list(WORDLIST)
        return self

    def generate(self) -> Safe_Str__Simple_Token:
        word1  = secrets.choice(self.words)
        word2  = secrets.choice(self.words)
        number = secrets.randbelow(10000)
        token_str = f'{word1}-{word2}-{number:04d}'
        return Safe_Str__Simple_Token(token_str)

    def word_count(self) -> int:
        return len(self.words)
