"""Add the two 1991 assembly sources to the archives that are ALREADY PUBLISHED.

make_archives.py rebuilds both archives from the pristine pre-cleaning source.
That source is gone: what survives is what went up to archive.org, plus the
fossil beside it.  Re-deriving a published artifact from a different input is
how byte differences creep in, so this does the delta instead -- every existing
member is copied through unchanged, and only the intended additions are made.

Same division of labour as make_archives.py, for the same reasons:

    both archives   get the two files, so the only difference between them
                    stays the virus (plus the fossil's own warning files)
    the clean one   also gets the README entries and the note, because it is
                    the documented public artifact; the fossil's README has
                    never carried the contributed-file notes

Run it twice and it refuses the second time rather than appending twice.

    python tools/add_sources.py [clean.zip] [fossil.zip] [out_dir]
"""

import os
import sys
import time
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_archives as MA

CLEAN_IN = r"C:\git\pctalker-archive.zip"
FOSSIL_IN = (r"C:\git\archive-build"
             r"\DO-NOT-RUN-INFECTED--pctalker-archive-with-DiskKiller-fossil.zip")
OUT = r"C:\git\archive-build2"

#: The 2026-08-19 grant, and only it.  Taken from make_archives so the two
#: tools cannot drift apart on what is permitted.
DIRECTORY, PREFIX, NAMES = MA.EXTRA_GROUPS[1]


def patch_readme(data):
    """Index the two sources in CONTENTS, then append the note."""
    text = data.decode("ascii")
    if MA.CONTENTS_ANCHOR2 not in text:
        raise SystemExit("README.txt: RAWSP anchor not found")
    text = text.replace(MA.CONTENTS_ANCHOR2,
                        MA.CONTENTS_ADD2 + MA.CONTENTS_ANCHOR2, 1)
    return (text.rstrip() + MA.SOURCES_NOTE).encode("ascii")


def extend(src_path, out_path, do_readme):
    src = zipfile.ZipFile(src_path)
    names = src.namelist()

    already = [PREFIX + n for n in NAMES if PREFIX + n in names]
    if already:
        raise SystemExit("%s already contains %s -- nothing to do"
                         % (os.path.basename(src_path), ", ".join(already)))
    if "The two 1991 sources" in src.read("README.txt").decode("ascii"):
        raise SystemExit("%s: README already carries the note"
                         % os.path.basename(src_path))

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            data = src.read(info.filename)
            if do_readme and info.filename == "README.txt":
                data = patch_readme(data)
                out = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                out.compress_type = zipfile.ZIP_DEFLATED
            else:
                out = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                out.compress_type = info.compress_type
                out.external_attr = info.external_attr
                out.internal_attr = info.internal_attr
                out.create_system = info.create_system
            dst.writestr(out, data)

        for name in NAMES:
            path = os.path.join(DIRECTORY, name)
            if not os.path.isfile(path):
                raise SystemExit("missing contributed file: %s" % path)
            info = zipfile.ZipInfo(
                PREFIX + name,
                date_time=time.localtime(os.path.getmtime(path))[:6])
            info.compress_type = zipfile.ZIP_DEFLATED
            with open(path, "rb") as fh:
                dst.writestr(info, fh.read())
            print("   + %s%s" % (PREFIX, name))

    src.close()
    print("   -> %s" % out_path)


def main():
    clean_in = sys.argv[1] if len(sys.argv) > 1 else CLEAN_IN
    fossil_in = sys.argv[2] if len(sys.argv) > 2 else FOSSIL_IN
    out_dir = sys.argv[3] if len(sys.argv) > 3 else OUT
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    print("clean:")
    extend(clean_in, os.path.join(out_dir, MA.CLEAN_NAME), do_readme=True)
    print("fossil:")
    extend(fossil_in, os.path.join(out_dir, MA.FOSSIL_NAME), do_readme=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
