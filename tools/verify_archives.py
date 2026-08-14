# -*- coding: utf-8 -*-
"""Prove the clean archive is clean and that nothing else moved.

Two separate claims, both worth checking before an upload that has already been
taken down once:

  1. No copy of the virus survives anywhere in the clean zip -- including
     inside the nested archives, which is where a shallow sweep would miss it.
  2. Every byte we did NOT mean to touch is unchanged, and every timestamp
     still matches, right down to members of the nested zips.

The signature sweep looks for the virus's CODE, not for the words "Disk
Killer": the README deliberately explains what was removed, and a checker that
cannot tell documentation from a specimen would force us to write a worse
README.  The two byte patterns below are the real thing, lifted from the
specimens at DEM1+0xBE00 and DEM2+0x13.  Neither can occur in prose.

    py -3 tools/verify_archives.py
"""

import hashlib
import io
import os
import sys
import zipfile

SRC = r"C:\git\pctalker-archive.zip"
CLEAN = r"C:\git\archive-build\pctalker-archive.zip"
FOSSIL = (r"C:\git\archive-build"
          r"\DO-NOT-RUN-INFECTED--pctalker-archive-with-DiskKiller-fossil.zip")

#: Disk Killer code, not its banner.  DEM1 0xBE00 is the entry (cli; cs: mov);
#: DEM2 0x13 is the rep movsb relocator that follows the message.
CODE = [
    bytes.fromhex("FA2EC60664018333C08ED8A12000A304"),
    bytes.fromhex("57B93A00BEA508BF0300FCF3A45FC3"),
]
#: Banner text.  Real inside a specimen, harmless inside documentation.
TEXT = [b"Disk Killer -- Version", b"I wish you luck !", b"COMPUTER OGRE"]
DOCS = (".txt", ".md", ".doc")

#: Bytes we intended to overwrite, and nothing else.
EXPECTED = {"DEM1": (0xBE00, 50002), "DEM2": (0x0000, 0x0400)}


def walk(zf, prefix=""):
    """Yield (path, bytes, date_time) for every file, descending into zips."""
    for info in zf.infolist():
        if info.is_dir():
            continue
        data = zf.read(info.filename)
        path = prefix + info.filename
        yield path, data, info.date_time
        if info.filename.lower().endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(data)) as sub:
                for item in walk(sub, path + "::"):
                    yield item


def collect(path):
    with zipfile.ZipFile(path) as zf:
        return {p: (d, t) for p, d, t in walk(zf)}


def scan(members):
    """(code hits, text hits in non-documentation members)."""
    code, text = [], []
    for p, (d, _) in members.items():
        for sig in CODE:
            if sig in d:
                code.append((p, sig[:8].hex()))
        if p.lower().endswith(DOCS):
            continue
        for sig in TEXT:
            if sig in d:
                text.append((p, sig))
    return code, text


def main():
    for p in (SRC, CLEAN, FOSSIL):
        if not os.path.isfile(p):
            print("missing:", p)
            return 1

    src, clean, fossil = collect(SRC), collect(CLEAN), collect(FOSSIL)
    fail = 0

    # -- 1. no specimen anywhere in the clean archive ----------------------
    print("1. signature sweep of the clean archive (%d members)" % len(clean))
    code, text = scan(clean)
    for p, h in code:
        fail = 1
        print("   FAIL %-44s virus code %s..." % (p, h))
    for p, s in text:
        fail = 1
        print("   FAIL %-44s banner %r" % (p, s))
    if not code and not text:
        print("   OK   no virus code, no banner outside documentation")

    fcode, _ = scan(fossil)
    ok = len(fcode) >= 2
    print("   fossil retains the specimen in %d member(s): %s"
          % (len(fcode), "OK" if ok else "FAIL -- fossil is not a fossil"))
    fail = fail or (not ok)

    # -- 2. nothing else changed -------------------------------------------
    print("\n2. diff against the source archive")
    if set(src) != set(clean):
        fail = 1
        print("   FAIL member list differs")
        for p in sorted(set(src) ^ set(clean)):
            print("        %s" % p)

    explained = set()
    for p in sorted(src):
        if p not in clean or src[p][0] == clean[p][0]:
            continue
        base = os.path.basename(p.split("::")[-1])
        sd, cd = src[p][0], clean[p][0]
        if base == "README.txt":
            print("   ok   %-42s note appended (+%d bytes)"
                  % (p, len(cd) - len(sd)))
            explained.add(p)
        elif base in EXPECTED:
            start, end = EXPECTED[base]
            good = (len(sd) == len(cd)
                    and sd[:start] == cd[:start] and sd[end:] == cd[end:]
                    and set(cd[start:end]) == {0x80})
            print("   %-4s %-42s %d bytes -> 0x80, rest intact"
                  % ("ok" if good else "FAIL", p, end - start))
            if good:
                explained.add(p)
            else:
                fail = 1

    # A nested container may differ only because a member inside it was cleaned.
    for p in sorted(src):
        if p in explained or p not in clean or src[p][0] == clean[p][0]:
            continue
        if p.lower().endswith(".zip") and any(
                q.startswith(p + "::") for q in explained):
            print("   ok   %-42s repacked around a cleaned member" % p)
            explained.add(p)
        else:
            fail = 1
            print("   FAIL %-42s unexplained change" % p)

    # -- 3. timestamps ------------------------------------------------------
    drift = [p for p in src if p in clean and src[p][1] != clean[p][1]]
    print("\n3. timestamps: %s"
          % ("all %d preserved" % len(clean) if not drift
             else "FAIL, %d drifted: %s" % (len(drift), drift[:5])))
    fail = fail or bool(drift)

    print("\n4. files")
    for label, p in (("clean ", CLEAN), ("fossil", FOSSIL)):
        with open(p, "rb") as fh:
            digest = hashlib.sha256(fh.read()).hexdigest()
        print("   %s %9d bytes  %s" % (label, os.path.getsize(p),
                                       os.path.basename(p)))
        print("          sha256 %s" % digest)

    print("\n%s" % ("ALL CHECKS PASSED" if not fail
                    else "*** FAILURES ABOVE ***"))
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
