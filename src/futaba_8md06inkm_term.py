from futaba_8md06inkm import VFD

NCHARS = 8

def clamp(x, l, u):
    return l if x < l else u if x > u else x

class Term:
    def __init__(self, drv):
        self._drv = drv
        self._cursoraddr = 0
        self._lastaddr = 0
        self._buffer = [' '] * NCHARS
        
    def cls(self, flush=True):
        self._buffer[:] = [' '] * NCHARS
        self._cursoraddr = 0
        self._lastaddr = 0
        if flush:
            self._drv.display_clear()

    def flush(self):
        self._drv.display_str(0, self._buffer)

    def home(self):
        self._cursoraddr = 0

    def pos(self) -> int:
        return self._cursoraddr
    
    def setpos(self, n):
        self._cursoraddr = clamp(n, 0, NCHARS-1)
    
    # write glyph (3 bytes) directly at position pos
    def direct(self, pos, glyph):
        # this causes all kinds of messy trouble
        
        #self._drv.display_str(pos, [chr(glyph[0])])
        pass

    def putchar(self, c):
        if c == '\n' or c == '\r':
            self.home()
            return
        elif c == '\014':   # ^L form feed
            self.cls(flush=False)
            return
        elif c == '\010': # ^H backspace
            self.setpos(self.pos() - 1)
            return
        
        if c == '\xb0': # degree char
            c = '\xef'
        
        # auto scroll
        self.autoscroll()

        self._lastaddr = self._cursoraddr
        self._buffer[self.pos()] = c
        self._cursoraddr += 1

    def puts(self, s, flush=True):
        for c in s:
            self.putchar(c)
        if flush:
            self.flush()

    def autoscroll(self):
        if self._cursoraddr >= NCHARS:
            self._buffer[0:NCHARS-1] = self._buffer[1:NCHARS]
            self._cursoraddr -= 1        

    def begin(self):
        pass

    def end(self):
        pass

    def setBrightness(self, brightness=7):
        self._drv.set_display_dimming(brightness * 36)

    def setDisplay(self, on):
        if on:
            self._drv.on()
        else:
            self._drv.off()
