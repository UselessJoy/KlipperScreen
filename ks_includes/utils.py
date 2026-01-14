from math import floor

def toReadableSeconds(seconds):
    h = floor(seconds / 3600)
    m = floor(seconds % 3600 / 60)
    s = floor(seconds % 3600 % 60)
    res = f"{h + ' ' + {_('h.') + ' '} if h else ''}{m} {_('min.')} {s} {_('sec.')}"
    return res

def toReadableLength(mmLen, showMicrons = False):
    if mmLen >= 1000:
        return f"{(mmLen / 1000):.2f} {_('m')}"
    if mmLen > 100:
        return f"{(mmLen / 10):.1f} {_('cm')}"
    if showMicrons and mmLen < 0.1:
        return f"{(mmLen * 1000):.0f} {_('μm')}"
    return f"{(mmLen):.1f} {_('mm')}"