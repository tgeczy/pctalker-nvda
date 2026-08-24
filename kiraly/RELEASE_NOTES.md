# PC-TALKER — Python rewrites by Király József

Three NVDA speech synthesizers, **written by Király József**, the author of
PC-TALKER, in August 2026. Published with his express permission.

## What is in this release

| Add-on | Version | The edition it rebuilds |
|---|---|---|
| PCTALKER Printer | 0.1.5 | 1989, parallel-port D/A converter |
| PCTALKER PC Speaker | 0.2.5.1 | 1990–91, internal speaker, PWM on the 8253 timer |
| PCTALKER Sound Blaster | 0.1.0 | 1991, the last version — improved intonation, recursive echo |

Install any or all three. They do not conflict, and each appears on its own in
NVDA's synthesizer list. **Sound Blaster is the one to read with**: it is the
final version, and the intonation work is in it.

## What these are

Not three alternatives — **three milestones toward the last one**. They sound
alike and each has a single voice, because they are the same synthesizer at
three points in its life. The sources show the shape: the printer and Sound
Blaster editions are the same file fourteen months apart, both headers still
naming the `OLvorauj.asm` they grew from and both playing `RAWHUSR`
(89.nov.5 and 91.jan.13); the PC speaker edition is the sibling branch,
`OLvassp.asm` with `RAWSP`, kept alive beside them to the end (91.jan.26).

**They are not emulated.** Each is a real NVDA synthesizer — a `synthDrivers`
module using NVDA's own WavePlayer and rate control. No DOS, no external
process. The author ported the logic of his own assembly, line by line, into
Python.

The assembly ships with them all the same, and is **parsed at run time**:
`OLVAS_P.ASM`, `OLVASSP.ASM` and `OLVAS_S.ASM` are where each add-on reads its
speech-element and conversion tables from. The source is the data file, not a
document in the package. The speech data is original too — `RAWHUSR` and
`RAWSP`, cut in 1987 from 8 kHz recordings of the author's own voice, and the
`SZOTAR.TBL` exception dictionary.

The PC Speaker add-on offers four variants of its voice, from a clean computed
envelope to true PWM with the small speaker's own filtering: the difference
between what the program calculated and what anyone actually heard.

## Related

- **The emulated add-on**, released separately from this same repository — the
  original 1990–91 DOS binaries under a CPU emulator. A reference build, for
  asking what the original programs really did, rather than for daily reading.
  The Sound Blaster rewrite here was checked against it: same echo, same pitch.
- [archive.org/details/pctalker-archive](https://archive.org/details/pctalker-archive)
  — the original programs, manuals, recordings and assembly sources.

## Credit

PC-TALKER and these three rewrites are the work of **Király József**. Packaging
and publication: tgeczy, at his request.

---

# PC-TALKER — Király József Python-változatai

Három NVDA-beszédszintetizátor, **Király József**, a PC-TALKER szerzőjének
munkája, 2026 augusztusából. Kifejezett engedélyével jelenik meg.

## Mi van ebben a kiadásban

| Bővítmény | Verzió | Melyik változatot építi újra |
|---|---|---|
| PCTALKER Printer | 0.1.5 | 1989, nyomtatóportra kötött D/A átalakító |
| PCTALKER PC Speaker | 0.2.5.1 | 1990–91, belső hangszóró, PWM a 8253 időzítőn |
| PCTALKER Sound Blaster | 0.1.0 | 1991, az utolsó verzió — javított intonáció, rekurzív visszhang |

Bármelyik telepíthető, akár mind a három. Nem ütköznek, és külön-külön jelennek
meg az NVDA szintetizátorlistájában. **Olvasáshoz a Sound Blaster való**: ez az
utolsó változat, és ebben van benne az intonációs munka.

## Mik ezek

Nem három alternatíva, hanem **három állomás az utolsó felé**. Hasonlóan
szólnak, és mindegyikben egyetlen hang van, mert ugyanannak a szintetizátornak
három állapotáról van szó. A források megmutatják az alakját: a nyomtatóportos
és a Sound Blaster-es változat ugyanaz a fájl tizennégy hónap különbséggel — a
fejlécükben máig az `OLvorauj.asm` neve áll, és mindkettő a `RAWHUSR`-t
szólaltatja meg (89.nov.5, illetve 91.jan.13) —, a hangszórós változat pedig a
testvérág: `OLvassp.asm` a `RAWSP`-vel, végig mellettük (91.jan.26).

**Nem emulációról van szó.** Mindegyik valódi NVDA-szintetizátor: `synthDrivers`
modul, az NVDA saját WavePlayerével és sebességszabályzójával. Nincs DOS, és
nincs külső program. A szerző a saját assemblyjének logikáját ültette át,
soronként, Pythonba.

Az assembly ettől még velük van, és **futás közben olvassa ki a program**: az
`OLVAS_P.ASM`, az `OLVASSP.ASM` és az `OLVAS_S.ASM` az, ahonnan mindegyik
bővítmény a hangelem- és átalakító táblázatait veszi. A forrás az adatfájl, nem
melléklet a csomagban. A hanganyag is eredeti — a `RAWHUSR` és a `RAWSP`,
amelyeket 1987-ben a szerző saját hangjáról készült 8 kHz-es felvételekből
vágott ki, valamint a `SZOTAR.TBL` kivételszótár.

A hangszórós bővítményben a hangnak négy variánsa választható, a tiszta,
számított burkolótól a valódi PWM-ig, a kis hangszóró saját szűrésével: vagyis a
különbség aközött, amit a program kiszámolt, és amit bárki hallott belőle.

## Kapcsolódó

- **Az emulált bővítmény**, ugyanennek a tárolónak a külön kiadásaként — az
  eredeti 1990–91-es DOS-programok processzoremulátorban. Referenciakiadás: arra
  való, hogy meg lehessen kérdezni, mit csináltak valójában az eredeti
  programok, nem napi olvasásra. Az itteni Sound Blaster-es újraírást ehhez
  mérve ellenőriztük: ugyanaz a visszhang, ugyanaz a hangmagasság.
- [archive.org/details/pctalker-archive](https://archive.org/details/pctalker-archive)
  — az eredeti programok, kézikönyvek, felvételek és assembly források.

## Köszönet

A PC-TALKER és ez a három újraírás **Király József** munkája. Csomagolás és
közzététel: tgeczy, az ő kérésére.
