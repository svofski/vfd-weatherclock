# pt6315
import asyncio

HAS_DOT = False

# PT6315 Display and Keymatrix data
PT6315_MAX_NR_GRIDS   = 12
PT6315_BYTES_PER_GRID =  3

# Significant bits Keymatrix data
PT6315_KEY_MSK      = 0xFF 

# Memory size in bytes for Display and Keymatrix
PT6315_DISPLAY_MEM_SZ = (PT6315_MAX_NR_GRIDS * PT6315_BYTES_PER_GRID)
PT6315_KEY_MEM      =   4

# Reserved bits for commands
PT6315_CMD_MSK      = 0xC0

# Mode setting command
PT6315_MODE_SET_CMD     = 0x00
PT6315_GR4_SEG24        = 0x00
PT6315_GR5_SEG23        = 0x01
PT6315_GR6_SEG22        = 0x02
PT6315_GR7_SEG21        = 0x03
PT6315_GR8_SEG20        = 0x04
PT6315_GR9_SEG19        = 0x05
PT6315_GR10_SEG18       = 0x06
PT6315_GR11_SEG17       = 0x07
PT6315_GR12_SEG16       = 0x08  # default

# Data setting commands
PT6315_DATA_SET_CMD  = 0x40
PT6315_DATA_WR       = 0x00
PT6315_LED_WR        = 0x01
PT6315_KEY_RD        = 0x02
PT6315_SW_RD         = 0x03
PT6315_ADDR_INC      = 0x00
PT6315_ADDR_FIXED    = 0x04
PT6315_MODE_NORM     = 0x00
PT6315_MODE_TEST     = 0x08

# LED settings data
PT6315_LED_MSK      = 0x0F
PT6315_LED1         = 0x01
PT6315_LED2         = 0x02
PT6315_LED3         = 0x04
PT6315_LED4         = 0x08

# Address setting commands
PT6315_ADDR_SET_CMD = 0xC0
PT6315_ADDR_MSK     = 0x3F

# Display control commands
PT6315_DSP_CTRL_CMD = 0x80
PT6315_BRT_MSK      = 0x07
PT6315_BRT0         = 0x00 # Pulsewidth 1/16, Default
PT6315_BRT1         = 0x01
PT6315_BRT2         = 0x02
PT6315_BRT3         = 0x03
PT6315_BRT4         = 0x04
PT6315_BRT5         = 0x05
PT6315_BRT6         = 0x06
PT6315_BRT7         = 0x07 # Pulsewidth 14/16

PT6315_BRT_DEF      = PT6315_BRT3

PT6315_DSP_OFF      = 0x00 # Default
PT6315_DSP_ON       = 0x08

# CONFIG
PT6315_VFD_LEFTPADDING = 0
VFD_NCHARS = 6

import font

def clamp(x, l, u):
    return l if x < l else u if x > u else x


class VFD:
    def __init__(self, drv):
        self._drv = drv
        
    def cls(self, nchars=PT6315_DISPLAY_MEM_SZ):
        self._drv.cls(nchars)

    def flush(self):
        self._drv.flush()

    def home(self):
        self._drv.setpos(0)

    def pos(self) -> int:
        return self._cursoraddr // 3
    
    # write glyph (3 bytes) directly at position pos
    def direct(self, pos, glyph):
        self._drv.direct(pos, glyph)

    def putchar(self, c):
        if c == '\n' or c == '\r':
            self.home()
            return
        elif c == '\014':   # ^L form feed
            self._drv.cls()
            return
        elif c == '\010': # ^H backspace
            self.setpos(self.pos() - 1)
            return
        
        # auto scroll
        self._drv.autoscroll()

        glyph = font.vfd_get_glyph(c)
        self._drv.putglyph(glyph)

    def puts(self, s, flush=True):
        for c in s:
            self.putchar(c)
        if flush:
            self.flush()

    def begin(self):
        self._drv.begin()

    def end(self):
        self._drv.end()

    def setBrightness(self, brightness=PT6315_BRT_DEF):
        self._drv.setBrightness(brightness)

    def setDisplay(self, on):
        self._drv.setDisplay(on)


class PT6315:
    pin_cs = -1
    spi = None
    _mode = PT6315_GR7_SEG21
    _display = PT6315_DSP_OFF
    _bright = PT6315_BRT0
    _leftpadding = PT6315_VFD_LEFTPADDING 
    _displaymem = bytearray(PT6315_DISPLAY_MEM_SZ)
    _lastaddr = 0
    _cursoraddr = 0

    def spiwrbyte(self, byte):
        self.spi.write(byte.to_bytes(1, 'little'))
    
    def __init__(self, spi, pin_cs, mode=PT6315_GR7_SEG21):
        self.spi = spi
        self.pin_cs = pin_cs
        self._mode = mode
        self.pin_cs.on()
        self._cursoraddr = 0
        self._lastaddr = 0

    def begin(self):
        self._writeCmd(PT6315_MODE_SET_CMD, self._mode)

    def end(self):
        pass

    def setBrightness(self, brightness=PT6315_BRT_DEF):
        self._bright = brightness & PT6315_BRT_MSK
        self._writeCmd(PT6315_DSP_CTRL_CMD, self._display | self._bright)

    def setDisplay(self, on):
        self._display = PT6315_DSP_ON if on else PT6315_DSP_OFF
        self._writeCmd(PT6315_DSP_CTRL_CMD, self._display | self._bright )

    def _writeCmd(self, cmd, data):
        self.pin_cs(0)
        try:
            self.spiwrbyte((cmd & PT6315_CMD_MSK) | (data & ~PT6315_CMD_MSK))
        finally:
            self.pin_cs(1)

    def direct(self, pos, glyph):
        # write glyph (3 bytes) directly at position pos
        self.pin_cs(0)
        try:
            self.spiwrbyte(PT6315_ADDR_SET_CMD | (pos * 3))
            for d in glyph:
                self.spiwrbyte(d)
        finally:
            self.pin_cs(1)

    def flush(self):
        self.pin_cs(0)
        try:
            self.spiwrbyte(PT6315_ADDR_SET_CMD | 0x00) # addr = 0

            for d in self._displaymem[0:VFD_NCHARS*3]:
                self.spiwrbyte(d)
        finally:
            self.pin_cs(1)

    def cls(self, nchars=PT6315_DISPLAY_MEM_SZ):
        self._displaymem[0:VFD_NCHARS * 3] = bytearray([0] * (VFD_NCHARS * 3))
        self.setpos(0)
        self.flush()

    def putglyph(self, glyph):
        self._lastaddr = self._cursoraddr
        self._displaymem[self._cursoraddr] = (glyph >> 16) & 255
        self._cursoraddr += 1
        self._displaymem[self._cursoraddr] = (glyph >> 8) & 255
        self._cursoraddr += 1
        self._displaymem[self._cursoraddr] = glyph & 255
        self._cursoraddr += 1

    def autoscroll(self):
        if self._cursoraddr >= VFD_NCHARS * 3:
            self._displaymem[0:(VFD_NCHARS-1) * 3] = self._displaymem[3:VFD_NCHARS * 3]
            self._cursoraddr -= 3

    def setpos(self, pos):
        self._cursoraddr = self._leftpadding * 3 + pos * 3
        self._cursoraddr = clamp(self._cursoraddr, 0, len(self._displaymem) - 1)
        self._lastaddr = self._cursoraddr

