# PC-TALKER for NVDA — the author's own Python rewrites

**Written by Király József**, the author of PC-TALKER, in August 2026.

> **Licence.** The MIT licence at the root of this repository covers the NVDA
> driver, the DOS host and the reverse engineering — not this directory. Everything
> under `kiraly/` is Király József's own work, published with his permission. He
> has stated no licence for it, and that is his to decide.

Three NVDA speech synthesizers, one for each edition of the Hungarian PC-TALKER
he wrote between 1989 and 1991. He rewrote all three himself, thirty-five years
later, from his own surviving assembly sources. Published here with his express
permission.

---

## Three add-ons, one lineage

They sound similar, and each offers a single voice. That is the point: they are
not three alternatives to choose between, they are **three milestones on the way
to the last one**.

| Add-on | Edition | Output in its day |
|---|---|---|
| **PCTALKER Printer** 0.1.5 | the earliest, 1989 | a D/A converter wired to the parallel port — the arrangement demonstrated at the 1988 Budapest fair |
| **PCTALKER PC Speaker** 0.2.5.1 | 1990–91 | the small internal speaker and nothing else: amplitude became pulse width on channel 2 of the 8253 timer |
| **PCTALKER Sound Blaster** 0.1.0 | 1991, the last | the Sound Blaster DSP, with improved punctuation intonation and a recursive echo |

The Sound Blaster edition is the one that went to market, and the one the author
calls the final version. Reading them in order is reading the problem being
solved: first get speech out of a machine at all, then get it out of a machine
with no sound hardware, then make it good.

The sources say how they are related, and it is not a simple ladder. The printer
and Sound Blaster editions are **the same file fourteen months apart** — both
headers still carry the name they grew from, `OLvorauj.asm`, and both play
`RAWHUSR`:

    OLVAS_P.ASM   Last update 89.nov.5     printer port
    OLVAS_S.ASM   Last update 91.jan.13    Sound Blaster

The PC speaker edition is the sibling branch, `OLvassp.asm` playing `RAWSP`, kept
alive alongside them right to the end:

    READSPF.ASM   Last update 89.maj.26    (in the archive)
    OLVASSP.ASM   Last update 91.jan.26

So the line that ends in the Sound Blaster version begins at the parallel port,
and the speaker edition is what happened when the same synthesizer had to work on
a machine with no sound hardware at all.

The PC Speaker add-on offers four **variants** of its one voice, from a clean
mathematically-derived envelope to true PWM with the small speaker's own
filtering — the difference between what the program computed and what anyone
actually heard.

## Not an emulator

Each add-on is a synthesizer in NVDA's own terms: a `synthDrivers` module,
NVDA's WavePlayer, NVDA's rate control. Nothing is emulated, no DOS is involved,
and there is no external process. The author ported the logic of his own
assembly, line by line, into Python.

The assembly did not stay behind, though. **Each add-on ships its original source
and parses it at run time** — `OLVAS_P.ASM`, `OLVASSP.ASM`, `OLVAS_S.ASM` — to
read out the speech-element and conversion tables it needs. The source is not
documentation sitting in the package. It is the data file. Delete it and the
add-on stops speaking.

The speech data is original too: `RAWHUSR` and `RAWSP`, the element banks cut in
1987 from 8 kHz recordings of the author's own voice, and `SZOTAR.TBL`, the
exception dictionary.

## Which one should I install?

Any of them, or all three — they do not conflict, and each appears separately in
NVDA's synthesizer list. For everyday reading, **Sound Blaster** is the one to
use: it is the last version, and it has the intonation work in it.

There is also a fourth add-on in this repository, one directory up, and it is a
different kind of thing: it runs the original 1990–91 DOS binaries under a CPU
emulator, byte for byte. That one is a reference — use it to ask what the
original programs actually did. These three are for reading with.

The two together are what make either trustworthy. The Sound Blaster rewrite was
checked against the 1991 binary running under emulation: same echo, same pitch.
In the author's own words:

> Az Ön által készített, az eredeti .exe fájlokat használó emuláció óriási érték,
> az én verzióim sem lennének hitelesek ezek nélkül.

## Archive

The original DOS programs, manuals, recordings and assembly sources are
preserved, with the author's permission, at
[archive.org/details/pctalker-archive](https://archive.org/details/pctalker-archive).

## Credit

PC-TALKER, all three editions, and these three Python rewrites are the work of
**Király József**. Packaging and publication: tgeczy, at his request.

---
---

# PC-TALKER NVDA alatt — a szerző saját Python-változatai

**Készítette Király József**, a PC-TALKER szerzője, 2026 augusztusában.

> **Licenc.** A tároló gyökerében lévő MIT licenc az NVDA-meghajtóra, a
> DOS-gazdaprogramra és a visszafejtésre vonatkozik — erre a mappára nem. A
> `kiraly/` alatt minden Király József saját munkája, az ő engedélyével közzétéve.
> Licencet nem kötött ki hozzá, és ez az ő döntése.

Három NVDA-beszédszintetizátor, egy-egy a magyar PC-TALKER mindhárom
változatához, amelyeket 1989 és 1991 között írt. Mindhármat ő maga írta újra,
harmincöt évvel később, a saját, megmaradt assembly forrásaiból. Kifejezett
engedélyével jelenik meg itt.

---

## Három bővítmény, egy fejlődési út

Hasonlóan szólnak, és mindegyikben egyetlen hang van. Éppen ez a lényeg: nem
három választható alternatíva, hanem **három állomás az utolsó felé vezető
úton**.

| Bővítmény | Változat | Amin annak idején megszólalt |
|---|---|---|
| **PCTALKER Printer** 0.1.5 | a legkorábbi, 1989 | a nyomtatóportra kötött D/A átalakító — az az elrendezés, amelyet 1988-ban a budapesti vásáron bemutatott |
| **PCTALKER PC Speaker** 0.2.5.1 | 1990–91 | a kis belső hangszóró és semmi más: az amplitúdó impulzusszélességgé vált a 8253 időzítő 2-es csatornáján |
| **PCTALKER Sound Blaster** 0.1.0 | 1991, az utolsó | a Sound Blaster DSP, javított írásjel-intonációval és rekurzív visszhanggal |

A Sound Blaster-es változat az, amelyik forgalomba került, és amelyet a szerző az
utolsó verziónak nevez. Sorban végighallgatni őket annyi, mint végignézni,
hogyan oldódik meg a feladat: előbb egyáltalán szólaljon meg a gép, aztán
szólaljon meg hangkártya nélkül is, végül szóljon jól.

A források elárulják, hogyan függenek össze — és ez nem egyszerű létra. A
nyomtatóportos és a Sound Blaster-es változat **ugyanaz a fájl, tizennégy hónap
különbséggel**: a fejlécük máig azt a nevet viseli, amelyikből nőttek,
`OLvorauj.asm`, és mindkettő a `RAWHUSR`-t szólaltatja meg:

    OLVAS_P.ASM   Last update 89.nov.5     nyomtatóport
    OLVAS_S.ASM   Last update 91.jan.13    Sound Blaster

A hangszórós változat a testvérág: `OLvassp.asm`, a `RAWSP`-vel, végig mellettük
életben tartva:

    READSPF.ASM   Last update 89.maj.26    (az archívumban)
    OLVASSP.ASM   Last update 91.jan.26

A Sound Blaster-es változatba torkolló vonal tehát a nyomtatóportnál kezdődik, a
hangszórós változat pedig az, ami akkor lett, amikor ugyanannak a
szintetizátornak hangkártya nélküli gépen is működnie kellett.

A hangszórós bővítményben az egy hangnak négy **variánsa** választható, a tiszta,
matematikailag számított burkolótól a valódi PWM-ig, a kis hangszóró saját
szűrésével együtt — vagyis a különbség aközött, amit a program kiszámolt, és
amit bárki hallott belőle.

## Ez nem emuláció

Mindegyik bővítmény a szó NVDA-beli értelmében szintetizátor: `synthDrivers`
modul, az NVDA saját WavePlayere, az NVDA sebességszabályzója. Semmi nem emulál,
nincs DOS, és nincs külső program. A szerző a saját assemblyjének a logikáját
ültette át, soronként, Pythonba.

Az assembly viszont nem maradt el. **Mindegyik bővítmény magával viszi az
eredeti forrását, és futás közben olvassa ki belőle** — `OLVAS_P.ASM`,
`OLVASSP.ASM`, `OLVAS_S.ASM` — a hangelem- és átalakító táblázatokat. A forrás
tehát nem dokumentáció a csomagban, hanem az adatfájl. Ha törli, a bővítmény
elnémul.

A hanganyag is eredeti: a `RAWHUSR` és a `RAWSP`, azok a hangelemtárak,
amelyeket 1987-ben a szerző saját hangjáról készült 8 kHz-es felvételekből
vágott ki, valamint a `SZOTAR.TBL` kivételszótár.

## Melyiket telepítsem?

Bármelyiket, vagy mind a hármat — nem ütköznek, és külön-külön jelennek meg az
NVDA szintetizátorlistájában. Napi olvasáshoz a **Sound Blaster** való: ez az
utolsó változat, és ebben van benne az intonációs munka.

Van egy negyedik bővítmény is ugyanebben a tárolóban, egy szinttel feljebb, de
az másfajta dolog: az eredeti 1990–91-es DOS-programokat futtatja
processzoremulátorban, bájtról bájtra. Az referencia — azzal lehet megkérdezni,
mit csináltak valójában az eredeti programok. Ez a három pedig arra való, hogy
olvassunk vele.

A kettő együtt teszi hitelessé egymást. A Sound Blaster-es újraírást az 1991-es,
emulátorban futó programhoz mérve ellenőriztük: ugyanaz a visszhang, ugyanaz a
hangmagasság. A szerző szavaival:

> Az Ön által készített, az eredeti .exe fájlokat használó emuláció óriási érték,
> az én verzióim sem lennének hitelesek ezek nélkül.

## Archívum

Az eredeti DOS-programok, kézikönyvek, felvételek és assembly források a szerző
engedélyével megőrizve:
[archive.org/details/pctalker-archive](https://archive.org/details/pctalker-archive).

## Köszönet

A PC-TALKER mindhárom változata és ez a három Python-újraírás **Király József**
munkája. Csomagolás és közzététel: tgeczy, az ő kérésére.
