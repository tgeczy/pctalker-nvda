# -*- coding: utf-8 -*-
"""Build the two release archives: one clean, one deliberately not.

Internet Archive restored https://archive.org/details/pctalker-archive on
2026-08-12 with the zip deleted, and asked for a clean replacement.  Two files
in it, DEM1 and DEM2, carry 2,560 bytes of the 1989 Disk Killer boot-sector
virus, written over the audio on the author's own diskette in 1990.  See
docs/diskkiller-forensics.md for how that was established.

    clean   pctalker-archive.zip
            The virus bytes replaced with 0x80 -- silence, since these are
            8-bit PCM centred on 128.  Byte ranges and file lengths are
            otherwise EXACTLY as the author sent them, so every offset in
            every file still matches the original.  Nothing of his is lost:
            his audio at those offsets was destroyed in 1990, and what we
            remove is the virus's own body.

    fossil  DO-NOT-RUN-INFECTED--pctalker-archive-with-DiskKiller-fossil.zip
            The archive exactly as it was, virus included, for anyone who
            wants to study it.  Not for archive.org.  The name is doing real
            work: it has to survive being downloaded, renamed and forgotten.

Timestamps are preserved everywhere, including inside the two nested archives,
which are unpacked and rebuilt entry by entry rather than copied.

    py -3 tools/make_archives.py [source.zip] [outdir]
"""

import hashlib
import io
import os
import sys
import time
import zipfile

SRC = r"C:\git\pctalker-archive.zip"
OUT = r"C:\git\archive-build"

CLEAN_NAME = "pctalker-archive.zip"
FOSSIL_NAME = "DO-NOT-RUN-INFECTED--pctalker-archive-with-DiskKiller-fossil.zip"

#: Added to BOTH archives, so the only difference between them stays the virus.
#: Permission was given per group: the 1989 printer set on 2026-08-14, the two
#: 1991 sources on 2026-08-19 ("Igen, az OLVAS_S.ASM es az OLVASSP.ASM fajlokat
#: is feltoltheti az archivumba").  His Python ports themselves are his own
#: current work and are covered by neither grant.
#:
#: (source directory, archive prefix, file names).  The printer set gets its own
#: folder because it is a whole edition that survives only as source; the two
#: 1991 files go to the root beside READSPF.ASM, because they are sources whose
#: binaries are already here.
EXTRA_GROUPS = (
    (r"C:\pctalker-archive\PCTALKER_PRINTER_1989", "PCTALKER_PRINTER_1989/",
     ("OLVAS_P.ASM", "RAWHUSR", "SZOTAR.TBL")),
    (r"C:\pctalker-archive", "", ("OLVASSP.ASM", "OLVAS_S.ASM")),
)

#: Silence.  These recordings are 8-bit unsigned PCM centred on 128, and both
#: boundaries already sit within a couple of counts of it, so the join is
#: inaudible -- no fade needed, and no fade wanted: a fade would alter samples
#: outside the virus region.
FILL = 0x80

#: What to overwrite, keyed by the SHA-256 of the infected original so this can
#: never run against the wrong file.  (start, end) is a half-open byte range.
INFECTED = {
    "DEM1": {
        "sha256": "0b7a93ad60be1a0003b270538e28396f"
                  "dcde0759bfd752d5c6432e7f78bf8168",
        "size": 50002,
        "region": (0xBE00, 50002),
        "expect": b"Disk Killer -- Version 1",
    },
    "DEM2": {
        "sha256": "5cc5e0d53fb59aa177a8d0e1afd86c41"
                  "6d33fb480ff696a5f2b5526fcbeae363",
        "size": 48002,
        "region": (0x0000, 0x0400),
        "expect": b"I wish you luck !",
    },
}


def clean_member(name, data):
    """Return `data` with the virus region blanked, or `data` unchanged.

    Refuses to touch anything whose hash, size or content is not exactly the
    specimen we characterised.  Silently cleaning the wrong file would destroy
    audio and nobody would notice for years.
    """
    spec = INFECTED.get(os.path.basename(name))
    if spec is None:
        return data, False
    digest = hashlib.sha256(data).hexdigest()
    if digest != spec["sha256"]:
        raise SystemExit(
            "%s does not match the known infected copy\n"
            "  expected %s\n  got      %s" % (name, spec["sha256"], digest))
    if len(data) != spec["size"]:
        raise SystemExit("%s is %d bytes, expected %d"
                         % (name, len(data), spec["size"]))
    start, end = spec["region"]
    if spec["expect"] not in data[start:end]:
        raise SystemExit("%s: %r not found in the region to be cleared"
                         % (name, spec["expect"]))
    out = bytearray(data)
    out[start:end] = bytes([FILL]) * (end - start)
    return bytes(out), True


def rebuild_nested(data, report):
    """Rebuild a nested .zip with its DEM1/DEM2 cleaned, timestamps kept.

    A nested archive with nothing to clean is returned untouched.  Repacking it
    would change every byte of the container for no reason -- these two zips are
    the author's own files, exactly as he sent them, and that is worth more than
    a consistent compressor setting.
    """
    src = zipfile.ZipFile(io.BytesIO(data))
    if not any(os.path.basename(i.filename) in INFECTED for i in src.infolist()):
        return data
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            payload = src.read(info.filename)
            payload, changed = clean_member(info.filename, payload)
            if changed:
                report.append("      %s" % info.filename)
            out = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            out.compress_type = info.compress_type
            out.external_attr = info.external_attr
            out.internal_attr = info.internal_attr
            out.create_system = info.create_system
            dst.writestr(out, payload)
    return buf.getvalue()


#: Slotted into the CONTENTS list rather than only appended, so the list stays
#: an accurate index of what is in the archive.
CONTENTS_ANCHOR = ("  original-archives/       The two packages exactly as "
                   "the author sent them.")
CONTENTS_ADD = """  PCTALKER_PRINTER_1989/   The 1989 PRINTER PORT edition, contributed by the
                           author in August 2026.  OLVAS_P.ASM is his assembly
                           source, RAWHUSR the speech element bank it plays,
                           and SZOTAR.TBL the exception dictionary as a
                           standalone table.  No binary of this edition is
                           known to survive; this source is what there is.
"""

PRINTER_NOTE = """

The 1989 printer port edition
-----------------------------

PCTALKER_PRINTER_1989/ arrived thirty-seven years after it was written.  In
August 2026 the author rewrote OLVAS_P.ASM into Python, so that PC-TALKER
could run on a modern machine with no emulation at all, and sent the original
assembly along with it.  These three files are that edition's complete source
and data.  The file dates are from his 2026 packaging, not from 1989.

It is the earliest PC-TALKER here and the only one with no surviving binary.
Its output path is a D/A converter on the parallel port -- the arrangement
demonstrated at the 1988 Budapest fair -- and the source documents its own
sample rates:

    timer1   db 05h     ;   4   kHz
    timer2   db 73h     ;   8.5 kHz
    timer3   db 9ch     ;  12   kHz

chosen by a byte carried with the sound file, falling back to 8.5 kHz.  That
is why this edition sits lower in pitch than the 1990-91 speaker and Sound
Blaster builds, which run at 9178 Hz.  Both are correct for their own version.

RAWHUSR and RAWSP are the SAME recordings: they correlate at 0.986 with no
offset and differ by two bytes in length.  RAWSP is the speaker edition's
copy, with its amplitudes and ratios adjusted by hand -- in the author's own
account, because after pulse width modulation the beeper circuit and the
speaker itself made that necessary.

---

Az 1989-es nyomtatoportos valtozat

A PCTALKER_PRINTER_1989/ mappa harminchet evvel a keszitese utan kerult elo.
2026 augusztusaban a szerzo atirta az OLVAS_P.ASM-et Pythonba, hogy a PCTALKER
emulacio nelkul is fusson mai gepen, es elkuldte hozza az eredeti assembly
forrast is.  Ez a harom fajl ennek a valtozatnak a teljes forrasa es adata.  A
fajlok datuma a 2026-os csomagolasbol szarmazik, nem 1989-bol.

Ez a legkorabbi itt szereplo PCTALKER, es az egyetlen, amelybol futtathato
peldany nem maradt fenn.  A hangot a nyomtatoportra kotott D/A atalakito adta
ki -- ez volt az 1988-as budapesti vasaron bemutatott megoldas -- es a forras
maga rogziti a mintaveteli frekvenciakat: 4, 8,5 es 12 kHz, a hangfajllal
erkezo bajt valasztja ki, alapertelmezesben 8,5 kHz.  Ezert szol ez a valtozat
melyebben, mint az 1990-91-es hangszoros es Soundblaster-es epitesek, amelyek
9178 Hz-en futnak.  Mindketto helyes a maga verziojahoz.

A RAWHUSR es a RAWSP UGYANAZ a felvetel: 0,986-os korrelacioval fedik egymast,
eltolas nelkul.  A RAWSP a hangszoros valtozat peldanya, kezzel igazitott
amplitudokkal es aranyokkal -- a szerzo szavaival azert, mert a
jelszelesseg-modulacio utan a beeper aramkor es a hangszoro sajatossagai ezt
megkoveteltek.
"""

README_NOTE = """

REMOVED: a fossilised virus, August 2026
----------------------------------------

Two files in this archive, DEM1 and DEM2, contained 2,560 bytes of the 1989
Disk Killer (Ogre) boot-sector virus.  It was not attached to any program: on
the author's own diskette in 1990 the virus wrote its body over one contiguous
five-sector run that straddled the end of DEM1 and the start of DEM2,
destroying about 0.26 seconds of his recordings.  He did not know until 2026.

In THIS copy those bytes are replaced with 0x80 -- silence.  File lengths are
unchanged and every other byte is exactly as he sent it, so all offsets still
match the originals.  Nothing of his was lost here that was not already lost
in 1990.

  DEM1  bytes 0xBE00..0xC351 (1362 bytes)   SHA-256 of the original:
        0b7a93ad60be1a0003b270538e28396fdcde0759bfd752d5c6432e7f78bf8168
  DEM2  bytes 0x0000..0x03FF (1024 bytes)   SHA-256 of the original:
        5cc5e0d53fb59aa177a8d0e1afd86c416d33fb480ff696a5f2b5526fcbeae363

The unmodified files are preserved separately for study.  The full forensic
account is at https://github.com/tgeczy/pctalker-nvda -- docs/diskkiller-
forensics.md.

---

ELTAVOLITVA: egy megkovesedett virus, 2026 augusztusa

Ket fajl, a DEM1 es a DEM2, az 1989-es Disk Killer (Ogre) boot-szektor virus
2560 bajtjat tartalmazta.  Nem fertozott programrol volt szo: 1990-ben, a
szerzo sajat lemezen, a virus egy osszefuggo ot szektoros savot irt felul,
amely atnyult a DEM1 vegerol a DEM2 elejere, es koruelbelul 0,26 masodpercnyi
felvetelt megsemmisitett.

Ebben a masolatban ezek a bajtok 0x80-ra, azaz csendre vannak cserelve.  A
fajlhosszak valtozatlanok, minden mas bajt pontosan ugy all, ahogy a szerzo
kuldte.  A serertetlen eredeti fajlok kulon, tanulmanyozas celjara megmaradtak.
"""

WARNING = """\
STOP.  READ THIS BEFORE YOU EXTRACT ANYTHING.
=============================================

THIS ARCHIVE CONTAINS A REAL COMPUTER VIRUS.  IT IS HERE ON PURPOSE.

Two files -- PCTAKER_SP/DEM1 and PCTAKER_SP/DEM2, and their copies under
PCTALKER_SP2/ and inside original-archives/ -- each contain part of the 1989
Disk Killer (also called Ogre) boot-sector virus, 2,560 bytes in total.

This copy exists for study.  A clean copy of the same archive, with those
bytes replaced by silence, is at:

    https://archive.org/details/pctalker-archive

USE THAT ONE unless you specifically want the virus.


WHAT IT IS

Disk Killer is a boot-sector infector from 1989.  It spread on floppies, and
after a number of reboots it scrambled the disk.  In 1990 it got onto Kiraly
Jozsef's development machine in Budapest while he was recording the demo audio
for his PC speaker speech synthesizer, and wrote its body over one contiguous
five-sector run straddling the end of DEM1 and the start of DEM2.  His audio
was underneath.  The evidence sat in his own files for thirty-six years.


WHY IT CANNOT HURT YOU HERE

  * It is a BOOT-SECTOR virus.  It infects the boot sector of a disk, not
    programs.  No executable in this archive is infected.
  * The 2,560 bytes sit inside DATA files that are only ever read as audio
    samples.  Nothing branches into them.  Playing the demos does not run it.
  * The copy is INCOMPLETE: 174 bytes are missing from the middle, lost as
    slack when DEM1 was copied off the diskette by length.
  * It is 16-bit real-mode code.  A 64-bit operating system cannot execute it
    at all, and it would have to reach a boot sector to get control anyway.

Your antivirus will still flag this file, correctly.  It is matching a real
signature on a real virus.


WHAT WOULD BE STUPID

Do not write DEM1 or DEM2 to the boot sector of anything.  Do not "restore"
them to a raw disk image.  If you study this in a DOS virtual machine, snapshot
it first and give it no writable disk you care about -- that is ordinary
hygiene for any DOS-era archive, and worth doing regardless of this file.

Separately, and nothing to do with the virus: OLVASSP.EXE has an undocumented
mode where a command tail beginning with "." is a disk SECTOR EDITOR that
issues INT 13h AH=03 writes.  Do not run "olvassp ." on real hardware.


FULL FORENSIC ACCOUNT

  https://github.com/tgeczy/pctalker-nvda   docs/diskkiller-forensics.md

  DEM1  50,002 bytes  virus at 0xBE00..0xC351
        sha256 0b7a93ad60be1a0003b270538e28396fdcde0759bfd752d5c6432e7f78bf8168
  DEM2  48,002 bytes  virus at 0x0000..0x03FF
        sha256 5cc5e0d53fb59aa177a8d0e1afd86c416d33fb480ff696a5f2b5526fcbeae363


=============================================
FIGYELEM!  EZ AZ ARCHIVUM VALODI SZAMITOGEPES VIRUST TARTALMAZ, SZANDEKOSAN.

Ket fajl, a DEM1 es a DEM2, az 1989-es Disk Killer (Ogre) boot-szektor virus
2560 bajtjat tartalmazza.  1990-ben, a felvetelek keszitesekor, a virus Kiraly
Jozsef gepen ratelepedett a hanganyagra.

Nem tud kart tenni: boot-szektor virus, tehat lemez inditoszektorat fertozi,
nem programot; az archivum egyetlen programja sem fertozott; a bajtok
adatfajlban vannak, amelyeket a program csak hangmintakent olvas; a masolat
hianyos; es 16 bites kod, amit mai 64 bites gep el sem tud inditani.

A megtisztitott valtozat itt talalhato:
    https://archive.org/details/pctalker-archive

Ezt a valtozatot csak tanulmanyozas celjara tartsuk meg.  Soha ne irjuk a DEM1
vagy DEM2 tartalmat lemez inditoszektoraba.
"""


#: Slotted beside READSPF.ASM rather than at the end, because OLVASSP.ASM is
#: literally the same file at a later date and belongs next to it.
CONTENTS_ANCHOR2 = ("  RAWSP                    The speech element bank of "
                    "the speaker edition.")
CONTENTS_ADD2 = """  OLVASSP.ASM              The SAME source as READSPF.ASM above, twenty
                           months later: "Last update 91.jan.26".  This is the
                           state OLVASSP.EXE was built from -- that binary is
                           dated 27 January 1991, the day after.  Contributed
                           by the author in August 2026.
  OLVAS_S.ASM              The Sound Blaster edition's source: "olvas_s.asm,
                           Last update 91.jan.13, hangfile = rawhusr".  The
                           source of PC-TALKER 5.01.  Contributed by the
                           author in August 2026.
"""

SOURCES_NOTE = """

The two 1991 sources
--------------------

OLVASSP.ASM and OLVAS_S.ASM arrived in August 2026, alongside the three add-ons
in which the author rewrote each edition into Python.  He gave permission to
archive them on 19 August 2026.  As with the printer folder, the file dates are
from his 2026 packaging; the dates that matter are the ones the sources state
about themselves.

With READSPF.ASM already here, the speaker edition is legible across its own
lifetime.  READSPF.ASM and OLVASSP.ASM are the same program -- both headers
call it OLvassp.asm -- caught twenty months apart:

    READSPF.ASM   Last update 89.maj.26    builds READSPF.EXE, 18 Mar 1990
    OLVASSP.ASM   Last update 91.jan.26    builds OLVASSP.EXE, 27 Jan 1991

3,474 of their lines are identical -- 89 percent of the older file, 93 percent
of the newer.  Diffing the two shows what the author changed between the 1990
and the 1991 speaker builds, in his own hand.

OLVAS_S.ASM is the other branch: the Sound Blaster edition, hangfile = rawhusr
instead of rawsp, last updated 13 January 1991 -- the day before the date on
PCTALKER_SB_Manual.DOC.  Its header still carries the name it forked from,
OLvorauj.asm.

---

A ket 1991-es forras

Az OLVASSP.ASM es az OLVAS_S.ASM 2026 augusztusaban kerult elo, azzal a harom
bovitmennyel egyutt, amelyekben a szerzo mindharom valtozatot atirta Pythonba.
Az archivalasukhoz 2026. augusztus 19-en jarult hozza.  A fajlok datuma itt is
a 2026-os csomagolasbol valo; ami szamit, azt a forrasok maguk mondjak meg
magukrol.

A READSPF.ASM-mel egyutt a hangszoros valtozat mostantol a sajat elettartamaban
olvashato.  A READSPF.ASM es az OLVASSP.ASM ugyanaz a program -- a fejlecukben
mindketto OLvassp.asm --, husz honap kulonbseggel:

    READSPF.ASM   Last update 89.maj.26    ebbol lett READSPF.EXE, 1990.03.18
    OLVASSP.ASM   Last update 91.jan.26    ebbol lett OLVASSP.EXE, 1991.01.27

3474 soruk azonos -- a regebbi fajl 89, az ujabb 93 szazaleka.  A kettot
osszevetve az latszik, mit valtoztatott a szerzo az 1990-es es az 1991-es
hangszoros valtozat kozott, a sajat kezevel.

Az OLVAS_S.ASM a masik ag: a Sound Blaster-es valtozat, hangfile = rawhusr a
rawsp helyett, utolso modositasa 1991. januar 13. -- egy nappal a
PCTALKER_SB_Manual.DOC datuma elott.  A fejlece meg mindig azt a nevet viseli,
amelyikbol kivalt: OLvorauj.asm.
"""


def patch_readme(data):
    """Index the new folder in CONTENTS, then append both notes.

    The README is deliberately plain ASCII, accents and all folded out, so it
    stays readable on the DOS-era machines this material came from.  Anything
    added here has to keep that.
    """
    text = data.decode("ascii")
    if CONTENTS_ANCHOR not in text:
        raise SystemExit("README.txt: CONTENTS anchor not found")
    text = text.replace(CONTENTS_ANCHOR, CONTENTS_ADD + CONTENTS_ANCHOR, 1)
    if CONTENTS_ANCHOR2 not in text:
        raise SystemExit("README.txt: RAWSP anchor not found")
    text = text.replace(CONTENTS_ANCHOR2, CONTENTS_ADD2 + CONTENTS_ANCHOR2, 1)
    return (text.rstrip() + PRINTER_NOTE + SOURCES_NOTE
            + README_NOTE).encode("ascii")


def add_extras(dst):
    """Write every contributed file into an open archive."""
    added = []
    for directory, prefix, names in EXTRA_GROUPS:
        for name in names:
            src = os.path.join(directory, name)
            if not os.path.isfile(src):
                raise SystemExit("missing contributed file: %s" % src)
            info = zipfile.ZipInfo(
                prefix + name,
                date_time=time.localtime(os.path.getmtime(src))[:6])
            info.compress_type = zipfile.ZIP_DEFLATED
            with open(src, "rb") as fh:
                dst.writestr(info, fh.read())
            added.append("%s%s" % (prefix, name))
    return added


def main():
    src_path = sys.argv[1] if len(sys.argv) > 1 else SRC
    out_dir = sys.argv[2] if len(sys.argv) > 2 else OUT
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    src = zipfile.ZipFile(src_path)
    infos = src.infolist()
    print("source: %s  (%d entries)" % (src_path, len(infos)))

    cleaned, report = [], []

    # -- clean copy, for archive.org ---------------------------------------
    clean_path = os.path.join(out_dir, CLEAN_NAME)
    with zipfile.ZipFile(clean_path, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in infos:
            data = src.read(info.filename)
            if info.filename == "README.txt":
                data = patch_readme(data)
            elif info.filename.lower().endswith(".zip"):
                sub = []
                data = rebuild_nested(data, sub)
                if sub:
                    report.append("    %s:" % info.filename)
                    report.extend(sub)
            else:
                data, changed = clean_member(info.filename, data)
                if changed:
                    cleaned.append(info.filename)
            out = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            out.compress_type = info.compress_type
            out.external_attr = info.external_attr
            out.internal_attr = info.internal_attr
            out.create_system = info.create_system
            dst.writestr(out, data)
        extras = add_extras(dst)

    print("\nclean -> %s" % clean_path)
    for n in extras:
        print("    + %s" % n)
    for n in cleaned:
        print("    %s" % n)
    for line in report:
        print(line)

    # -- fossil copy, for study -------------------------------------------
    fossil_path = os.path.join(out_dir, FOSSIL_NAME)
    forensics = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "docs", "diskkiller-forensics.md")
    with zipfile.ZipFile(fossil_path, "w", zipfile.ZIP_DEFLATED) as dst:
        dst.writestr("!!!-READ-ME-FIRST-DO-NOT-RUN.txt", WARNING)
        if os.path.isfile(forensics):
            with open(forensics, "rb") as fh:
                dst.writestr("diskkiller-forensics.md", fh.read())
        for info in infos:
            out = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            out.compress_type = info.compress_type
            out.external_attr = info.external_attr
            out.internal_attr = info.internal_attr
            out.create_system = info.create_system
            dst.writestr(out, src.read(info.filename))
        # the fossil stays a strict superset: same contents, virus intact, so
        # the only difference between the two archives is the 2,560 bytes
        add_extras(dst)
    print("\nfossil -> %s" % fossil_path)
    src.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
