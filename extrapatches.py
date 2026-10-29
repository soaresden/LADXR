"""Patches by other authors, applied on top of a generated rom.

Their authors don't allow shipping them with other files, so the player
supplies the patch file (--extra-patch, or the page's options). A patch is
recognized by its SHA-256, and only the part known to be safe on a randomized
rom is applied: the font tiles, or the palettes.
"""
import hashlib

FONT_BANKS = (0x0F, 0x2F)  # the font and its copy read by the Game Boy Color
FONT_START, FONT_END = 0x1000, 0x1A00  # tiles $00-$9F
# Accented lowercase letters: the same letters in every version's font.
SHARED_ACCENT_TILES = range(0x47, 0x54)
PALETTES_BANK = 0x21

KNOWN = {
    "c05274fcda0772adbf5ad48f6345467c919f473aa67db3048029fb78bd0eb56c": ("Font Improvement v1.2 by Tzepish", "font"),
    "bd9be04a7be4a5f5b52e88c54abb5f7834893bd724f3f2b62f84534b36062963": ("GBA Enhanced by Jayro", "palettes"),
    "765b6978ae824db687cacd30b42e20296a9d1e9855010fe484314173455ce499": ("Turbo-Français v1.4 by kemenaran", "language"),
}
# Turbo-Français is made for the French v1.1 (Rev A) ROM.
FRENCH_REV_A_CHECKSUM = 89757956


def _identify(patch):
    digest = hashlib.sha256(patch).hexdigest()
    if digest not in KNOWN:
        raise ValueError("Unknown extra patch (sha256 %s), supported: %s" % (digest, ", ".join(name for name, _ in KNOWN.values())))
    return KNOWN[digest]


def patchLanguageRom(language_rom, patch):
    """Apply a patch made for the language ROM (Turbo-Français) before it is
    used as language ROM. Other patches leave it as it is."""
    name, kind = _identify(patch)
    if kind != "language":
        return language_rom
    if sum(language_rom) != FRENCH_REV_A_CHECKSUM:
        raise ValueError("%s needs the French v1.1 (Rev A) ROM as language ROM" % (name))
    print("Extra patch: %s" % (name))
    data = bytearray(language_rom)
    for offset, record in readIps(patch):
        data[offset:offset + len(record)] = record
    return bytes(data)


def apply(rom, patch, english, language=None):
    name, kind = _identify(patch)
    if kind == "language":
        if language is None:
            raise ValueError("%s needs a French language ROM (--language-rom)" % (name))
        return
    print("Extra patch: %s" % (name))
    if kind == "font":
        _applyFont(rom, readIps(patch), english, language)
    elif kind == "palettes":
        _applyPalettes(rom, applyBps(patch, english), english)


def _applyFont(rom, records, english, language):
    # With a language rom, its own tiles stay: menu words like EFFACER/COPIER,
    # letters only that language has.
    keep = set()
    if language:
        for bank in FONT_BANKS:
            for tile in range(0xA0):
                addr = FONT_START + tile * 16
                if tile not in SHARED_ACCENT_TILES and \
                        language.rom.bank(bank)[addr:addr + 16] != english[bank * 0x4000 + addr:bank * 0x4000 + addr + 16]:
                    keep.add((bank, tile))
    for offset, data in records:
        for n, value in enumerate(data):
            bank, addr = divmod(offset + n, 0x4000)
            if bank in FONT_BANKS and FONT_START <= addr < FONT_END and (bank, (addr - FONT_START) // 16) not in keep:
                rom.banks[bank][addr] = value


def _applyPalettes(rom, target, english):
    start, end = PALETTES_BANK * 0x4000, (PALETTES_BANK + 1) * 0x4000
    for n in range(start, end):
        if target[n] != english[n]:
            rom.banks[PALETTES_BANK][n - start] = target[n]


def readIps(patch):
    assert patch[:5] == b"PATCH"
    idx, records = 5, []
    while patch[idx:idx + 3] != b"EOF":
        offset = int.from_bytes(patch[idx:idx + 3], "big")
        size = int.from_bytes(patch[idx + 3:idx + 5], "big")
        idx += 5
        if size == 0:
            size = int.from_bytes(patch[idx:idx + 2], "big")
            records.append((offset, bytes([patch[idx + 2]]) * size))
            idx += 3
        else:
            records.append((offset, patch[idx:idx + size]))
            idx += size
    return records


def applyBps(patch, source):
    # The source checksum isn't checked: GBA Enhanced is made for English
    # v1.2, whose palettes bank is the same as v1.0.
    assert patch[:4] == b"BPS1"
    idx = 4

    def number():
        nonlocal idx
        result, shift = 0, 1
        while True:
            byte = patch[idx]
            idx += 1
            result += (byte & 0x7F) * shift
            if byte & 0x80:
                return result
            shift <<= 7
            result += shift

    number()
    target = bytearray(number())
    metadata_size = number()
    idx += metadata_size
    out = source_rel = target_rel = 0
    while idx < len(patch) - 12:
        command = number()
        action, length = command & 3, (command >> 2) + 1
        if action == 0:
            target[out:out + length] = source[out:out + length]
        elif action == 1:
            target[out:out + length] = patch[idx:idx + length]
            idx += length
        else:
            delta = number()
            delta = -(delta >> 1) if delta & 1 else delta >> 1
            if action == 2:
                source_rel += delta
                target[out:out + length] = source[source_rel:source_rel + length]
                source_rel += length
            else:
                target_rel += delta
                for n in range(length):
                    target[out + n] = target[target_rel]
                    target_rel += 1
        out += length
    return target
