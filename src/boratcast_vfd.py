class Boratcast:
    _terms = []
    
    def __init__(self, terms):
        self._terms = terms
        
    def cls(self, flush=True):
        for t in self._terms:
            t.cls(flush)

    def flush(self):
        for t in self._terms:
            t.flush()

    def home(self):
        for t in self._terms:
            t.home()

    def pos(self) -> int:
        p = 0
        for t in self._terms:
            return t.pos()
        return p
    
    def setpos(self, n):
        for t in self._terms:
            t.setpos(n)
    
    # write glyph (3 bytes) directly at position pos
    def direct(self, pos, glyph):
        for t in self._terms:
            t.direct(pos, glyph)

    def putchar(self, c):
        for t in self._terms:
            t.putchar(c)

    def puts(self, s, flush=True):
        for t in self._terms:
            t.puts(s, flush=flush)

    def begin(self):
        for t in self._terms:
            t.begin()

    def end(self):
        for t in self._terms:
            t.end()

    def setBrightness(self, brightness=255):
        for t in self._terms:
            t.setBrightness(brightness)

    def setDisplay(self, on):
        for t in self._terms:
            t.setDisplay(on)
    