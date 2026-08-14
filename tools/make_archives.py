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
import zipfile

SRC = r"C:\git\pctalker-archive.zip"
OUT = r"C:\git\archive-build"

CLEAN_NAME = "pctalker-archive.zip"
FOSSIL_NAME = "DO-NOT-RUN-INFECTED--pctalker-archive-with-DiskKiller-fossil.zip"

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
                data = data.rstrip() + README_NOTE.encode("ascii")
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

    print("\nclean -> %s" % clean_path)
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
    print("\nfossil -> %s" % fossil_path)
    src.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
