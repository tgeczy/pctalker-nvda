;
; ****************************************************************
; *  uj                                                          *
; *  OLvorauj.asm                         Last update 91.jan.13  *
; *  olvas_s.asm      -       hangfile = rawhusr                 *
; *  sound-blaster verzio                ( rovid hangok )        *
; *                                                              *
; *                                                              *
; *                                                              *
; *            portc automatikus beallitasa                      *
; *            automatikus sebesseg beallitas                    *
; *            standard input olvasas Ctrl C -ig                 *
; *            sebesseg modositasi elehetoseg                    *
; *            kodolhatosag      Alt 255 utan                    *
; *                                      Alt 195                 *
; *                                      Alt 61                  *
; *                                      Alt 23                  *
; *                                                              *
; *           A leforditas utan az olvas.exe  es rawhusr filekat *
; *           kimasolni egy formattalt lemezre, majd DEBUG -al   *
; *           betenni a fileba a rawhusr -et. Ha DSEG valtozik,  *
; *           akkor a kodolo rutinokat is modositani kell. ?     *
; *                                                              *
; *           nemet verzio - uj convert  rutin amely tetszoleges *
; *           betukombinacio figyeleset lehetove teszi, cimzett  *
; *           szotarkezeles                                      *
; *                                                              *
; *                                                              *
; *           lej†tsz†si sebessÇg automatikus beallit†sa a       *
; *           hangfile alapjan, dekompressalas                   *
; *                                                              *
; *                                                              *
; *                                                              *
; *                                                              *
; ****************************************************************
;    Iras  a  digital-analog converterre - cim :      210
;    ----                                        vagy
;                                                     310
;
;             visszaolvasaskor a fenti cimekrol a 0-6 biteken a kiirt
;             adatot olvashatjuk vissza, a 7-es bit 8 kHz-el allapotot
;   nem       valt. Ezt a hetes bitet hasznaljuk a D/A konverter es az
;   hasznal   A/D koverter meghajtasi sebesseg beallitasara is.
;   juk !!!
;
;    Olvasas az analog-digital konverterrol - cim      211
;    -------                                      vagy
;                                                      311
;
; ****************************************************************



portseg segment at 0040h
        org 8
portcim dw  ?
portseg ends


interrupts      segment at 0h           ;address of the keyboard rutin
                org     9h*4
keyboard_int    label   dword
interrupts      ends


rom_bios_data   segment  at  40h
                org        1ah
                head       dw ?
                tail       dw ?
                buffer     dw  16 dup(?)   ; keyboard buffer
                buffer_end label word
rom_bios_data   ends


dseg     segment
; -----------------------------------

portc    dw 0378h

writec   dw  210h

readc    dw  211h
speed    dw 0
speedpl  dw 0
speedmn  dw 0
speedstp dw 0
speeddig dw 0
start    dw 0
hossz    dw 0
pontkov  dw 0
veszkov  dw 0
ejtes    dw 0
keses    dw 250
mult10   dw   1
fej      dw 0
farok    dw 0
timer    db 73h   ; 8.5 khz
timer1   db 05h     ;   4   kHz
timer2   db 73h     ;   8.5 kHz
timer3   db 9ch     ;  12   kHz
tomind   db 0
maxdi    dw 0
timersz  db 73h   ; 8.5 khz  szintetizator eseten
startclock db 0
fkodin   db 60    ; bufsize
kodhossz db 60    ; beolvasott karakterek szama
felhkod  db 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa '
         db   ' ', 7,0dh,0ah,'$'
polvasva dw 0
jelszo   db 10
         db 0
passw    db '1234567890'
         db   ' ', 7,0dh,0ah,'$'


maxch    equ  80
bufsize  db   maxch
num      db   5
bufr     db   maxch dup (' ')
term     db   0dh,0ah,'$'
;
filnam   db   'rawhusr',0,0dh,0ah,'$'
zar      db   1
         db   ' '
;
textlgt  db   0
textout  db   256 dup (' '),0dh,0ah,'$'
;
phonlgt  db   0
phonout  db   256 dup (' '),0dh,0ah,'$'
phnext   dw   0
phons    db   0
         db   160 dup (' '),0dh,0ah,'$'
phnexts  dw   0
sax      dw   0
ssi      dw   0
ssax      dw   0
sssi      dw   0
slszo     dw   0
sdi      dw   0
sisave   dw   0
;
virus    db   'A program virussal fertìzìdîtt ! ','$'
msg1     db   'Start  : ','$'
msg2     db   'Hossz  : ','$'
msg3     db   ' ',7,'Szîveg : ','$'
beepm    db   ' ',7,'$'
clock    db   0
crerr    db    'File megnyit†si hiba ',0dh,0ah,'$'
karderr  db    'PC-TALKER k†rtya hiba ! ',7,7,7,0dh,0ah,'$'
bufrr    db   58000 dup ('.')
         db  0dh,0ah,'$'
jumptbl  dw  0
cdown    dw  0
buffl    dw  0
mspeed   dw  0
htblptr  dw  0
htblptrn dw  0
htbl     dw  1200 dup ('::')


messcop  db           '    [44m …ÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕª ','[0m', 0dh,0ah
         db           '    [44m ∫  [1mPC-TALKER[0m[44m Sound-Blaster verzi¢ 5.01 ∫ ','[0m', 0dh,0ah
         db           '    [44m ÃÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕπ ','[0m', 0dh,0ah
         db           '    [44m ÃÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕπ ','[0m', 0dh,0ah
         db           '    [44m ∫ Copyright (c) 1991   Kir†ly J¢zsef   ∫ ','[0m', 0dh,0ah
         db           '    [44m ∫ 1121 Budapest, FÅlemÅle ut 12-18,5/B ∫ ','[0m', 0dh,0ah
         db           '    [44m ∫ HUNGARY                              ∫ ','[0m', 0dh,0ah
         db           '    [44m »ÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕÕº ','[0m', 0dh,0ah,'$'


sorok    db   ' ', 7,0dh,0ah,0dh,0ah,0dh,0ah,0dh,0ah,0dh,0ah,'$'

;
; szotar tablahoz tartozo adatok
; -------------------------------------
;

spind    db   0
szamind  db   0
lszo     dw   0

;
; hang tabla : hang start cim, hossz
c000c    dw  27622,1000   ; cs
c001c    dw  13240,1000   ; sz
c002c    dw  33591,1040   ; zs
c003c    dw  24903,1000   ; ty
c004c    dw  18604,1013   ; ny
c005c    dw  15876,832    ; ly
c006c    dw  23875,1000   ; gy
c007c    dw  25922,1620   ; dz
c008c    dw     50,1800    ; dzs
c009c    dw     50,1800
c010c    dw     50,1800
c011c    dw     50,1800
c012c    dw     50,1800
c013c    dw     50,1800
c014c    dw     50,1800
c015c    dw     50,1800
c016c    dw     50,1800
c017c    dw     50,1800
c018c    dw     50,1800
c019c    dw     50,1800
c020c    dw     50,1800
c021c    dw     50,1800
c022c    dw     50,1800
c023c    dw     50,1800
c024c    dw     50,1800
c025c    dw     50,1800
c026c    dw     50,1800
c027c    dw     50,1800
c028c    dw     50,1800
c029c    dw     50,1800
c030c    dw     50,1800
c031c    dw     50,1800
c032cbl  dw     50,200    ; blank
c033c    dw     50,1800
c034c    dw     50,1800
c035c    dw     50,1800
c036c    dw     50,1800    ; $
c037c    dw     50,1800    ; %
c038c    dw     50,1800
c039c    dw     50,1800
c040c    dw     50,1800
c041c    dw     50,1800
c042c    dw     50,1800
c043cpl  dw     50,1800    ; +
c044c    dw     50,1800
c045cmn  dw     50,1800    ; -
c046c    dw     50,1800
c047cpr  dw     50,1800    ; /
c048c0   dw     50,1800
c049c1   dw     50,1800
c050c2   dw     50,1800
c051c3   dw     50,1800
c052c4   dw     50,1800
c053c5   dw     50,1800
c054c6   dw     50,1800
c055c7   dw     50,1800
c056c8   dw     50,1800
c057c9   dw     50,1800
c058c    dw     50,1800
c059c    dw     50,1800
c060c    dw     50,1800       ; <
c061c    dw     50,1800       ; =
c062c    dw     50,1800       ; >
c063c    dw     50,1800       ; ?
c064c    dw     50,1800
c065cA   dw    1863,801
c066cB   dw   30965,800
c067cC   dw   19637,800
c068cD   dw   31956,800
c069cE   dw    3676,800
c070cF   dw   30146,800
c071cG   dw   20447,800
c072cH   dw   35456,820
c073cI   dw   10138,798
c074cJ   dw   15876,832
c075cK   dw   22231,800
c076cL   dw   34641,804
c077cM   dw    8484,811
c078cN   dw    9307,820
c079cO   dw    5526,811
c080cP   dw   23045,800
c081cQ   dw   36436,1600      ;     q
c082cR   dw   32761,820
c083cS   dw   14258,800
c084cT   dw   21411,800
c085cU   dw    7442,804
c086cV   dw   17762,827
c087cW   dw   17762,827
c088cX   dw   28632,1500       ;     x
c089cY   dw   10138,798
c090cZ   dw   16718,824
c091c    dw     50,1800
c092c    dw     50,1800
c093c    dw     50,1800
c094c    dw     50,1800
c095c    dw     50,1800
c096c    dw     50,1800
c097ca   dw    1863,801
c098cb   dw   30965,800
c099cc   dw   19637,800
c100cd   dw   31956,800
c101ce   dw    3676,800
c102cf   dw   30146,800
c103cg   dw   20447,800
c104ch   dw   35456,820
c105ci   dw   10138,798
c106cj   dw   15876,832
c107ck   dw   22231,800
c108cl   dw   34641,804
c109cm   dw    8484,811
c110cn   dw    9307,820
c111co   dw    5526,811
c112cp   dw   23045,800
c113cq   dw   36436,1600
c114cr   dw   32761,820
c115cs   dw   14258,800
c116ct   dw   21411,800
c117cu   dw    7442,804
c118cv   dw   17762,827
c119cw   dw   17762,827
c120cx   dw   28632,1500
c121cy   dw   10138,798
c122cz   dw   16718,824
c123c    dw     50,1800
c124c    dw     50,1800
c125c    dw     50,1800
c126c    dw     50,1800
c127c    dw     50,1800
c128c    dw     50,1800
c129cuuu dw  12172,805          ;       Å
c130cee  dw   4492,1017         ;       Ç
c131caa  dw  11152,1006         ;       ì
c132c    dw     50,1800
c133c    dw     50,1800
c134caa  dw   2673,995          ;       Ü
c135c    dw     50,1800
c136cee  dw   4492,1017         ;       à
c137c    dw     50,1800
c138c    dw     50,1800
c139c    dw   11152,1006        ;       ì <- ã
c140ci   dw   10138,1009        ;       å
c141ci   dw   10138,1009        ;       ç
c142c    dw     50,1800
c143caa  dw   2673,995          ;       è
c144cee  dw   4492,1017         ;       ê
c145c    dw     50,1800
c146c    dw     50,1800
c147co_o dw  11152,1006         ;       ì
c148cooo dw  15064,797          ;       î
c149c    dw     50,1800
c150cuuu dw   12172,1060        ;       ñ
c151cuu  dw    7442,1013        ;       ó
c152c    dw   12172,1060        ;       ñ
c153cooo dw  15064,797          ;       ô
c154cuuu dw  12172,805          ;       ö
c155c    dw     50,1800
c156c    dw     50,1800
c157c    dw     50,1800
c158c    dw     50,1800
c159c    dw     50,1800
c160caa  dw   2673,995          ;       †
c161cii  dw  10138,1009         ;       °
c162coo  dw   6350,1080         ;       ¢
c163cuu  dw   7442,1013         ;       £
c164c    dw     50,1800
c165c    dw     50,1800
c166c    dw     50,1800
c167c    dw     50,1800
c168c    dw     50,1800
c169c    dw     50,1800
c170c    dw     50,1800
c171c    dw     50,1800
c172c    dw     50,1800
c173c    dw     50,1800
c174c    dw     50,1800
c175c    dw     50,1800
c176c    dw     50,1800
c177c    dw     50,1800
c178c    dw     50,1800
c179c    dw     50,1800
c180c    dw     50,1800
c181c    dw 38500,500         ; hangjegyek
c182c    dw 39000,500
c183c    dw 39500,500
c184c    dw 40000,500
c185c    dw 40500,500
c186c    dw 41000,500
c187c    dw 41500,500
c188c    dw 42000,500
c189c    dw 42500,500
c190c    dw 43000,500
c191c    dw 43500,500
c192c    dw 44000,500
c193c    dw 44500,500
c194c    dw 45000,500
c195c    dw 45500,500
c196c    dw     50,1800
c197c    dw     50,1800
c198c    dw     50,1800
c199c    dw     50,1800
c200c    dw     50,1800
c201c    dw     50,1800
c202c    dw     50,1800
c203c    dw     50,1800
c204c    dw     50,1800
c205c    dw     50,1800
c206c    dw     50,1800
c207c    dw     50,1800
c208c    dw     50,1800
c209c    dw     50,1800
c210c    dw     50,1800
c211c    dw     50,1800
c212c    dw     50,1800
c213c    dw     50,1800
c214c    dw     50,1800
c215c    dw     50,1800
c216c    dw     50,1800
c217c    dw     50,1800
c218c    dw     50,1800
c219c    dw     50,1800
c220c    dw     50,1800
c221c    dw     50,1800
c222c    dw     50,1800
c223c    dw     50,1800
c224c    dw     50,1800
c225c    dw     50,1800
c226c    dw     50,1800
c227c    dw     50,1800
c228c    dw     50,1800
c229c    dw     50,1800
c230c    dw     50,1800
c231c    dw     50,1800
c232c    dw     50,1800
c233c    dw     50,1800
c234c    dw     50,1800
c235c    dw     50,1800
c236c    dw     50,1800
c237c    dw     50,1800
c238c    dw     50,1800
c239c    dw     50,1800
c240c    dw     50,1800
c241c    dw     50,1800
c242c    dw     50,1800
c243c    dw     50,1800
c244c    dw     50,1800
c245c    dw     50,1800
c246c    dw     50,1800
c247c    dw     50,1800
c248c    dw     50,1800
c249c    dw     50,1800
c250c    dw     50,1800
c251c    dw     50,1800
c252c    dw     50,1800
c253c    dw     50,1800
c254c    dw     50,1800
c255c    dw     50,1800
;

;
;   itt kovetkezik az egyes betukombinaciokat megado tabla
;


ctar     db   2, 'cs            ',  1,0,'             '
         db   3, 'ccs           ',  2,0,0,'            '
         db   2, 'Cs            ',  1,0,'             '
         db   2, 'cS            ',  1,0,'             '
         db   2, 'CS            ',  1,0,'             '
         db   0, '              ',  0, '              '

ktar     db   6, 'kîzsÇg        ',  6, 'kîssÇg        '
         db   6, 'KîzsÇg        ',  6, 'KîssÇg        '
         db   0, '              ',  0, '              '

star     db   2, 'sz            ',  1, '             '
         db   3, 'ssz           ',  2, '            '
         db   2, 'Sz            ',  1, '             '
         db   2, 'sZ            ',  1, '             '
         db   2, 'SZ            ',  1, '             '
         db   0, '              ',  0, '              '
ztar     db   2, 'zs            ',  1, '             '
         db   3, 'zzs           ',  2, '            '
         db   2, 'Zs            ',  1, '             '
         db   2, 'zS            ',  1, '             '
         db   2, 'ZS            ',  1, '             '
         db   2, 'zt            ',  2, 't            '
         db   0, '              ',  0, '              '
ttar     db   2, 'ty            ',  1, '             '
         db   3, 'tty           ',  2, '            '
         db   2, 'Ty            ',  1, '             '
         db   2, 'tY            ',  1, '             '
         db   2, 'TY            ',  1, '             '
         db   0, '              ',  0, '              '
ntar     db   2, 'ny            ',  1, '             '
         db   3, 'nny           ',  2, '            '
         db   2, 'Ny            ',  1, '             '
         db   2, 'nY            ',  1, '             '
         db   2, 'NY            ',  1, '             '
         db   0, '              ',  0, '              '
ltar     db   2, 'ly            ',  1, 'j             '
         db   2, 'Ly            ',  1, 'j             '
         db   2, 'lY            ',  1, 'j             '
         db   2, 'LY            ',  1, 'j             '
         db   3, 'lly           ',  1, 'j             '
         db   0, '              ',  0, '              '
gtar     db   2, 'gy            ',  1, '             '
         db   3, 'ggy           ',  2, '            '
         db   2, 'Gy            ',  1, '             '
         db   2, 'gY            ',  1, '             '
         db   2, 'GY            ',  1, '             '
         db   6, 'GAZSèG        ',  6, 'gazs†g        '
         db   6, 'gazs†g        ',  6, 'gazs†g        '
         db   6, 'Gazs†g        ',  6, 'gazs†g        '
         db   0, '              ',  0, '              '
dtar     db   2, 'dj            ',  1, '             '
         db   0, '              ',  0, '              '
vtar     db   5, 'vizsz         ',  5, 'viz          '
         db   5, 'Vizsz         ',  5, 'viz          '
         db   5, 'VIZSZ         ',  5, 'viz          '
         db   0, '              ',  0, '              '
mntar    db   2, '-t            ',  1, 't             '
         db   0, '              ',  0, '              '

         db   0, '              ',  0, '              '


;
dseg    ends



;  itt kovetkeznek a szamkonverzio adatai


szamds  segment
; -------------------------------------

include szotar.tbl
;
;
;



szam    db      0,'                   '
        db      3,'egy                '
        db      5,'kettì              '
        db      5,'h†rom              '
        db      4,'nÇgy               '
        db      2,'ît                 '
        db      3,'hat                '
        db      3,'hÇt                '
        db      5,'nyolc              '
        db      6,'kilenc             '

        db      0,'                   '
        db      8,'eggyedik           '
        db      8,'kettedik           '
        db      8,'harmadik           '
        db      8,'negyedik           '
        db      6,'îtîdik             '
        db      7,'hatodik            '
        db      7,'hetedik            '
        db      9,'nyolcadik          '
        db     10,'kilencedik         '         ; 1,20

        db      0,'                   '
        db      6,'eggyed             '
        db      6,'ketted             '
        db      6,'harmad             '
        db      6,'negyed             '
        db      4,'îtîd               '
        db      5,'hatod              '
        db      5,'heted              '
        db      7,'nyolcad            '
        db      8,'kilenced           '         ; 1,30

        db      0,'                   '
        db      3,'tiz                '
        db      4,'husz               '
        db      7,'harminc            '
        db      7,'negyven            '
        db      5,'îtven              '
        db      6,'hatvan             '
        db      6,'hetven             '
        db      8,'nyolcvan           '
        db      9,'kilencven          '

        db      0,'                   '
        db      7,'tizedik            '
        db      8,'huszadik           '
        db     11,'harmincadik        '
        db     11,'negyvenedik        '
        db      9,'îtvenedik          '
        db     10,'hatvanadik         '
        db     10,'hetvenedik         '
        db     12,'nyolcvanadik       '
        db     13,'kilencvenedik      '            ; 2,20

        db      0,'                   '
        db      5,'tized              '
        db      6,'huszad             '
        db      9,'harmincad          '
        db      9,'negyvened          '
        db      7,'îtvened            '
        db      8,'hatvanad           '
        db      8,'hetvened           '
        db     10,'nyolcvanad         '
        db     11,'kilencvened        '            ; 2,30

        db      0,'                   '
        db      7,'egysz†z            '
        db      9,'kettìsz†z          '
        db      9,'h†romsz†z          '
        db      8,'nÇgysz†z           '
        db      6,'îtsz†z             '
        db      7,'hatsz†z            '
        db      7,'hÇtsz†z            '
        db      9,'nyolcsz†z          '
        db     10,'kilencsz†z         '

        db      0,'                   '
        db     11,'egysz†zadik        '
        db     13,'kettîsz†zadik      '
        db     13,'h†romsz†zadik      '
        db     12,'nÇgysz†zadik       '
        db     10,'îtsz†zadik         '
        db     11,'hatsz†zadik        '
        db     11,'hÇtsz†zadik        '
        db     13,'nyolcsz†zadik      '
        db     14,'kilencsz†zadik     '            ; 3,20

        db      0,'                   '
        db      6,'sz†zad             '
        db     11,'kettîsz†zad        '
        db     11,'h†romsz†zad        '
        db     10,'nÇgysz†zad         '
        db      8,'îtsz†zad           '
        db      9,'hatsz†zad          '
        db      9,'hÇtsz†zad          '
        db     11,'nyolcsz†zad        '
        db     12,'kilencsz†zad       '            ; 3,30

        db      0,'                   '
        db      2,'en                 '
        db      2,'on                 '
        db      0,'                   '
        db      0,'                   '
        db      0,'                   '
        db      0,'                   '
        db      0,'                   '
        db      0,'                   '
        db      0,'                   '            ; 4,10
        db      0,'                   '
        db      0,'                   '
        db      0,'                   '
        db      0,'                   '
        db      0,'                   '
        db      0,'                   '
        db      0,'                   '
        db      0,'                   '
        db      0,'                   '
        db      0,'                   '            ; 4,20
        db      0,'                   '
        db      0,'                   '
        db      0,'                   '
        db      0,'                   '
        db      0,'                   '
        db      0,'                   '
        db      0,'                   '
        db      0,'                   '
        db      0,'                   '
        db      0,'                   '            ; 4,30

szne    db      7,' tized             '
        db      8,' sz†zad            '
        db      7,' ezred             '
        db     10,' tizezred          '
        db     11,' sz†zezred         '
        db     11,' milliomod         '
        db     14,' tizmilliomod      '
        db     15,' sz†zmilliomod     '
        db     12,' milli†rdod        '
        db     15,' tizmilli†rdod     '
        db     16,' sz†zmilli†rdod    '
        db     11,' billiomod         '
        db     14,' tizbilliomod      '
        db     15,' sz†zbilliomod     '
        db     12,' trilliomod        '
        db     15,' tiztrilliomod     '
        db     16,' sz†ztrilliomod    '
        db     15,' kvadrilliomod     '
        db     18,' tizkvadrilliomod  '
        db     19,' sz†zkvadrilliomod '


sznev   db      0,'                   '
        db      0,'                   '
        db      0,'                   '
        db      5,'ezer               '
        db      5,'ezer               '
        db      5,'ezer               '
        db      7,'milli¢             '
        db      7,'milli¢             '
        db      7,'milli¢             '
        db      9,'milli†rd           '

        db      9,'milli†rd           '
        db      9,'milli†rd           '
        db      7,'billi¢             '
        db      7,'billi¢             '
        db      7,'billi¢             '
        db      8,'trilli¢            '
        db      8,'trilli¢            '
        db      8,'trilli¢            '
        db     11,'kvadrilli¢         '
        db     11,'kvadrilli¢         '

        db      0,'                   '
        db      0,'                   '
        db      0,'                   '
        db      9,'ezredik            '
        db      9,'ezredik            '
        db      9,'ezredik            '
        db     13,'milliomodik        '
        db     13,'milliomodik        '
        db     13,'milliomodik        '
        db     16,'milli†rdomodik     '
        db     16,'milli†rdomodik     '
        db     16,'milli†rdomodik     '
        db     12,'billiomodik        '
        db     12,'billiomodik        '
        db     12,'billiomodik        '
        db     14,'trilliomodik       '
        db     14,'trilliomodik       '
        db     14,'trilliomodik       '
        db     16,'kvadrilliomodik    '
        db     16,'kvadrilliomodik    '

        db      0,'                   '
        db      0,'                   '
        db      0,'                   '
        db      5,'ezred              '
        db      5,'ezred              '
        db      5,'ezred              '
        db      9,'milliomod          '
        db      9,'milliomod          '
        db      9,'milliomod          '
        db     12,'milli†rdomod       '
        db     12,'milli†rdomod       '
        db     12,'milli†rdomod       '
        db     10,'billiomod          '
        db     10,'billiomod          '
        db     10,'billiomod          '
        db     11,'trilliomod         '
        db     11,'trilliomod         '
        db     11,'trilliomod         '
        db     14,'kvadrilliomod      '
        db     14,'kvadrilliomod      '


string1 db       0
        db       80 dup (' ')
szamstr db       0
        db       80 dup (' ')

stegesz db      0
        db      40 dup (' ')
sttort  db      0
        db      40 dup (' ')

sorsz   db       0
subl    db       0
sorsz1  db       0
lsep    db       0
index   db       0
lsubl   db       0
lindex  db       0
cpos    db       0
maradek db       0

plussz  db       0
        db       256 dup (' ')
told    db       0
        db      160 dup (' ')
csop    db       0
        db      160 dup (' ')

phone   db       0
        db       256 dup (' ')
phont   db       0
        db       256 dup (' ')
phon    db       0
        db       256 dup (' ')
space   db       2
        db       '  '
space1  db       1
        db       ' '

egesz   db       7,' egÇsz '
nulla   db       6,' nulla'

nulladik db      10,' nulladik '
elso     db       6,' elsì '
masodik  db       9,' m†sodik '
sok      db       7,'  sok  '
sokadik  db      11,'  sokadik  '
valahanyad db    32,'  valaminek a valahanyad rÇsze  '

messg1  db       'Irja be az †talakitand¢ sz†mot : ','$'
term2   db       0dh,0ah,'$'
nextl   db       3,0dh,0ah,'$'

buffinm db       80                   ; a buffer merete
buffinl db       0                    ; a beolvasott karakterek szama
buffin  db       80 dup (' ')

munka1  db       0


;  szamkonverzio adatainak vege
;
szamds   ends

;
;


hangds    segment   para
fname     db   '         ',0,0dh,0ah,'$'
          db   30 dup (0)
hangbuf   db   5000 dup (127)       ;;;;;;;;      60100 dup (127),'$'
hanglgt   dw  0
tom1     db   10000000b
tom2     db   01000000b
tom3     db   00100000b
tom4     db   00010000b
tom5     db   00001000b
tom6     db   00000100b
tom7     db   00000010b
tom8     db   00000001b
posszam  db 0
negszam  db 0
hangds    ends

tomds     segment  para
tombuf    db  7                      ;;;;;;;;      7800  dup (127),'$'
tomlgt    dw  0
tomds     ends



SSEG     SEGMENT STACK
         dw 200h dup (?)
SSEG     ENDS

cseg     segment

;
;

; macros for the system

init    macro   csname,dsname,ssname
        assume  cs:csname,ds:dsname,ss:ssname
        push    ds
        sub     ax,ax
        push    ax
        mov     ax,dseg
        mov     ds,ax
        mov     es,ax
        endm

prompt  macro   messge
        lea     dx,messge
        mov     ah,09
        int     21h
        endm

rclf    macro
        lea    dx,term
        mov    ah,9
        int    21h
        endm

beep    macro
        lea    dx,beepm
        mov    ah,9
        int    21h
        endm

valasz  macro  inpbuff
        lea    dx,inpbuff
        mov    ah,10
        int    21h
        endm

movstr  macro  honnan,hova
        local  jmovstr,exit
        mov    cx,0
        mov    cl,ds:honnan
        jcxz   jmovstr
        inc    cx
        lea    si,ds:honnan          ; a hosszat is atirjuk
        lea    di,es:hova
        cld
        rep movsb
        jmp    exit

jmovstr:
        mov    es:hova,0
exit:
        endm


movelem macro  hova               ; honnan az si -bol derul ki
        local  noelem,exit
        mov    cx,0
        mov    cl,[si]
        jcxz   noelem
        inc    cx
        lea    di,hova
        cld
        rep movsb
        jmp    exit
noelem: mov    hova,0

exit:
        endm


appnd   macro  mit,hova
        local  jappnd
        mov    cx,0
        mov    cl,mit
        jcxz   jappnd
        lea    si,mit             ; a hosszat nem irjuk at
        inc    si
        lea    di,hova
        inc    di
        mov    ax,0
        mov    al,hova
        add    di,ax
        add    hova,cl
        cld
        rep movsb
jappnd:
        endm


appelem macro  hova              ;  mit az si -ben megadva
        local  jappe
        mov    cx,0
        mov    cl,[si]
        jcxz   jappe
        inc    si                ;  a hosszat nem irjuk at
        lea    di,hova
        inc    di
        mov    ax,0
        mov    al,hova
        add    di,ax
        add    hova,cl
        cld
        rep movsb
jappe:
        endm



cls     macro
        mov    ax,3
        int    10h
        endm

sub30   macro  stringc
        local  csub30,jsub30,kesz1
        mov    cx,0
        mov    cl,stringc
        mov    si,offset stringc
        inc    si
        jcxz   kesz1
csub30: mov    al,[si]
        sub    al,30h
        cmp    al,9
        jbe    jsub30
        mov    al,0
jsub30: mov    [si],al
        inc    si
        loop   csub30
kesz1:
        endm

valax   macro  stringc,startpos,hossz
        local  lvalax,kszv
        mov    cx,0
        mov    cl,startpos
        dec    cx
        mov    si,offset stringc
        inc    si
        add    si,cx
        mov    cx,0
        mov    cl,hossz
        mov    ax,0
        jcxz   kszv
lvalax: mov    bl,[si]
        add    al,bl
        inc    si
        loop   lvalax
kszv:                       ; eredmeny az AX -ben
        endm




;
;  end of macros
;
pspseg   dw   0
old_keyboard_int        dd    ?
dssave   dw   0
essave   dw   0
sssave   dw   0
spsave   dw   0
stail    dw   0
shead    dw   0
elsoit   dw   0
joutit   dw   0

         assume cs:cseg, ds:dseg,ss:sseg

;
;
;
convert  proc                              ; forditas phonetikusra
         mov   si,0
         mov   di,0
     ;   dec   textlgt
         mov   bx,0
         mov   bl,textlgt
         mov   textout[bx],' '
         inc   bx
         mov   textout[bx],' '
         inc textlgt

ciklcv:
         mov   bx,0
         mov   bl,textout[si]

         ;                              ha file nev akkor atalakitas nelkul
         ;                              atpakoljuk
                cmp   bl,'&'
         ;      jne   nemnev
                jmp   nemnev
                mov    phonout[di],bl  ;  nev kezdodik
                inc    si
                inc    di
                inc    phonlgt

natir:          mov    bx,0            ;  vegtest
                mov    bl,textlgt
                cmp    si,bx
                jbe    nutolso
                jmp    over
nutolso:        mov    bl,textout[si]
                mov    phonout[di],bl
                inc    si
                inc    di
                inc    phonlgt
                cmp    bl,' '
                jne    natir
                jmp    endtest
         ;

nemnev:
         mov   al,bl
         mov   ah,al
         shl   bx,1
         mov    sdi,di
         mov    ssi,si
         mov    sax,ax
         push   ds
         pop    es
         assume cs:cseg, ds:dseg, es:dseg
         jmp   word ptr cs:[bx]+jumptable
;
jumptable  label word
           dw jumpc000           ; cs
           dw jumpc001           ; sz
           dw jumpc002           ; zs
           dw jumpc003           ; ty
           dw jumpc004           ; ny
           dw jumpc005           ; ly
           dw jumpc006           ; gy
           dw jumpc007           ; dz
           dw jumpc008           ; dzs
           dw jumpc009
           dw jumpc010
           dw jumpc011
           dw jumpc012
           dw jumpc013
           dw jumpc014
           dw jumpc015
           dw jumpc016
           dw jumpc017
           dw jumpc018
           dw jumpc019
           dw jumpc020
           dw jumpc021
           dw jumpc022
           dw jumpc023
           dw jumpc024
           dw jumpc025
           dw jumpc026
           dw jumpc027
           dw jumpc028
           dw jumpc029
           dw jumpc030
           dw jumpc031
           dw jumpc032
           dw jumpc033
           dw jumpc034
           dw jumpc035
           dw jumpc036
           dw jumpc037
           dw jumpc038
           dw jumpc039
           dw jumpc040
           dw jumpc041
           dw jumpc042
           dw jumpc043
           dw jumpc044
           dw jumpc045
           dw jumpc046
           dw jumpc047
           dw jumpc048
           dw jumpc049
           dw jumpc050
           dw jumpc051
           dw jumpc052
           dw jumpc053
           dw jumpc054
           dw jumpc055
           dw jumpc056
           dw jumpc057
           dw jumpc058
           dw jumpc059
           dw jumpc060
           dw jumpc061
           dw jumpc062
           dw jumpc063
           dw jumpc064
           dw jumpc065
           dw jumpc066
           dw jumpc067
           dw jumpc068
           dw jumpc069
           dw jumpc070
           dw jumpc071
           dw jumpc072
           dw jumpc073
           dw jumpc074
           dw jumpc075
           dw jumpc076
           dw jumpc077
           dw jumpc078
           dw jumpc079
           dw jumpc080
           dw jumpc081
           dw jumpc082
           dw jumpc083
           dw jumpc084
           dw jumpc085
           dw jumpc086
           dw jumpc087
           dw jumpc088
           dw jumpc089
           dw jumpc090
           dw jumpc091
           dw jumpc092
           dw jumpc093
           dw jumpc094
           dw jumpc095
           dw jumpc096
           dw jumpc097
           dw jumpc098
           dw jumpc099
           dw jumpc100
           dw jumpc101
           dw jumpc102
           dw jumpc103
           dw jumpc104
           dw jumpc105
           dw jumpc106
           dw jumpc107
           dw jumpc108
           dw jumpc109
           dw jumpc110
           dw jumpc111
           dw jumpc112
           dw jumpc113
           dw jumpc114
           dw jumpc115
           dw jumpc116
           dw jumpc117
           dw jumpc118
           dw jumpc119
           dw jumpc120
           dw jumpc121
           dw jumpc122
           dw jumpc123
           dw jumpc124
           dw jumpc125
           dw jumpc126
           dw jumpc127
           dw jumpc128
           dw jumpc129
           dw jumpc130
           dw jumpc131
           dw jumpc132
           dw jumpc133
           dw jumpc134
           dw jumpc135
           dw jumpc136
           dw jumpc137
           dw jumpc138
           dw jumpc139
           dw jumpc140
           dw jumpc141
           dw jumpc142
           dw jumpc143
           dw jumpc144
           dw jumpc145
           dw jumpc146
           dw jumpc147             ; hosszu ooo
           dw jumpc148
           dw jumpc149
           dw jumpc150             ; ñ
           dw jumpc151
           dw jumpc152
           dw jumpc153              ; ooo
           dw jumpc154              ; ö
           dw jumpc155
           dw jumpc156
           dw jumpc157
           dw jumpc158
           dw jumpc159
           dw jumpc160
           dw jumpc161
           dw jumpc162
           dw jumpc163              ; £
           dw jumpc164
           dw jumpc165
           dw jumpc166
           dw jumpc167
           dw jumpc168
           dw jumpc169
           dw jumpc170
           dw jumpc171
           dw jumpc172
           dw jumpc173
           dw jumpc174
           dw jumpc175
           dw jumpc176
           dw jumpc177
           dw jumpc178
           dw jumpc179
           dw jumpc180
           dw jumpc181             ; hangjegyek
           dw jumpc182
           dw jumpc183
           dw jumpc184
           dw jumpc185
           dw jumpc186
           dw jumpc187
           dw jumpc188
           dw jumpc189
           dw jumpc190
           dw jumpc191
           dw jumpc192
           dw jumpc193
           dw jumpc194
           dw jumpc195
           dw jumpc196
           dw jumpc197
           dw jumpc198
           dw jumpc199
           dw jumpc200
           dw jumpc201
           dw jumpc202
           dw jumpc203
           dw jumpc204
           dw jumpc205
           dw jumpc206
           dw jumpc207
           dw jumpc208
           dw jumpc209
           dw jumpc210
           dw jumpc211
           dw jumpc212
           dw jumpc213
           dw jumpc214
           dw jumpc215
           dw jumpc216
           dw jumpc217
           dw jumpc218
           dw jumpc219
           dw jumpc220
           dw jumpc221
           dw jumpc222
           dw jumpc223
           dw jumpc224
           dw jumpc225
           dw jumpc226
           dw jumpc227
           dw jumpc228
           dw jumpc229
           dw jumpc230
           dw jumpc231
           dw jumpc232
           dw jumpc233
           dw jumpc234
           dw jumpc235
           dw jumpc236
           dw jumpc237
           dw jumpc238
           dw jumpc239
           dw jumpc240
           dw jumpc241
           dw jumpc242
           dw jumpc243
           dw jumpc244
           dw jumpc245
           dw jumpc246
           dw jumpc247
           dw jumpc248
           dw jumpc249
           dw jumpc250
           dw jumpc251
           dw jumpc252
           dw jumpc253
           dw jumpc254
           dw jumpc255

 ; itt kovetkezik majd a fonetikus konverzio ahol szukseges

jumpc000:                   ;          cs
jumpc001:                   ;          sz
jumpc002:                   ;          zs
jumpc003:                   ;          ty
jumpc004:                   ;          ny       atkonvertalas utan majd
jumpc005:                   ;          ly       ezeknek a kettos massalhnak
jumpc006:                   ;          gy       ezek a kodok felelnek meg.
jumpc007:                   ;          dz
jumpc008:                   ;          dzs
jumpc009:                   ;
jumpc010:                   ;
jumpc011:                   ;
jumpc012:                   ;
jumpc013:                   ;
jumpc014:                   ;
jumpc015:                   ;
jumpc016:                   ;
jumpc017:                   ;
jumpc018:                   ;
jumpc019:                   ;
jumpc020:                   ;
jumpc021:                   ;
jumpc022:                   ;
jumpc023:                   ;
jumpc024:                   ;
jumpc025:                   ;
jumpc026:                   ;
jumpc027:                   ;
jumpc028:                   ;
jumpc029:                   ;
jumpc030:                   ;
jumpc031:                   ;
jumpc032:                   ;bl        blank
jumpc033:                   ;
jumpc034:                   ;
jumpc035:                   ;
jumpc036:                   ;          $
jumpc037:                   ;          %
jumpc038:                   ;
jumpc039:                   ;
jumpc040:                   ;
jumpc041:                   ;
jumpc042:                   ;
jumpc043:                   ;pl        +
jumpc044:                   ;
; jumpc045:                   ;mn        -
jumpc046:                   ;
jumpc047:                   ;pr        /
jumpc048:                   ;0
jumpc049:                   ;1
jumpc050:                   ;2
jumpc051:                   ;3
jumpc052:                   ;4
jumpc053:                   ;5
jumpc054:                   ;6
jumpc055:                   ;7
jumpc056:                   ;8
jumpc057:                   ;9
jumpc058:                   ;
jumpc059:                   ;
jumpc060:                   ;            <
jumpc061:                   ;            =
jumpc062:                   ;            >
jumpc063:                   ;            ?
jumpc064:                   ;
jumpc065:                   ;A
jumpc066:                   ;B
; jumpc067:                   ;C
; jumpc068:                   ;D
jumpc069:                   ;E
jumpc070:                   ;F
; jumpc071:                   ;G
jumpc072:                   ;H
jumpc073:                   ;I
jumpc074:                   ;J
; jumpc075:                   ;K
; jumpc076:                   ;L
jumpc077:                   ;M
; jumpc078:                   ;N
jumpc079:                   ;O
jumpc080:                   ;P
jumpc081:                   ;Q
jumpc082:                   ;R
; jumpc083:                   ;S
; jumpc084:                   ;T
jumpc085:                   ;U
; jumpc086:                   ;V
jumpc087:                   ;W
jumpc088:                   ;X
jumpc089:                   ;Y
;  jumpc090:                   ;Z
jumpc091:                   ;
jumpc092:                   ;
jumpc093:                   ;
jumpc094:                   ;
jumpc095:                   ;
jumpc096:                   ;
jumpc097:                   ;a
jumpc098:                   ;b
; jumpc099:                   ;c
; jumpc100:                   ;d
jumpc101:                   ;e
jumpc102:                   ;f
; jumpc103:                   ;g
jumpc104:                   ;h
jumpc105:                   ;i
jumpc106:                   ;j
; jumpc107:                   ;k
; jumpc108:                   ;l
jumpc109:                   ;m
; jumpc110:                   ;n
jumpc111:                   ;o
jumpc112:                   ;p
jumpc113:                   ;q
jumpc114:                   ;r
; jumpc115:                   ;s
; jumpc116:                   ;t
jumpc117:                   ;u
; jumpc118:                   ;v
jumpc119:                   ;w
jumpc120:                   ;x
jumpc121:                   ;y
;  jumpc122:                   ;z
jumpc123:                   ;
jumpc124:                   ;
jumpc125:                   ;
jumpc126:                   ;
jumpc127:                   ;
jumpc128:                   ;
jumpc129:                   ;uuu
jumpc130:                   ;ee
jumpc131:                   ;aa
jumpc132:                   ;
jumpc133:                   ;
jumpc134:                   ;aa
jumpc135:                   ;
jumpc136:                   ;ee
jumpc137:                   ;
jumpc138:                   ;
jumpc139:                   ;
jumpc140:                   ;i
jumpc141:                   ;i
jumpc142:                   ;
jumpc143:                   ;aa
jumpc144:                   ;ee
jumpc145:                   ;
jumpc146:                   ;
jumpc147:                   ;o_o         hosszu ooo
jumpc148:                   ;ooo
jumpc149:                   ;
jumpc150:                   ;uuu         ñ
jumpc151:                   ;uu
jumpc152:                   ;
jumpc153:                   ;ooo         ooo
jumpc154:                   ;uuu         ö
jumpc155:                   ;
jumpc156:                   ;
jumpc157:                   ;
jumpc158:                   ;
jumpc159:                   ;
jumpc160:                   ;aa
jumpc161:                   ;ii
jumpc162:                   ;oo
jumpc163:                   ;uu          £
jumpc164:                   ;
jumpc165:                   ;
jumpc166:                   ;
jumpc167:                   ;
jumpc168:                   ;
jumpc169:                   ;
jumpc170:                   ;
jumpc171:                   ;
jumpc172:                   ;
jumpc173:                   ;
jumpc174:                   ;
jumpc175:                   ;
jumpc176:                   ;
jumpc177:                   ;
jumpc178:                   ;
jumpc179:                   ;
jumpc180:                   ;
jumpc181:                   ;            hangjegyek
jumpc182:                   ;
jumpc183:                   ;
jumpc184:                   ;
jumpc185:                   ;
jumpc186:                   ;
jumpc187:                   ;
jumpc188:                   ;
jumpc189:                   ;
jumpc190:                   ;
jumpc191:                   ;
jumpc192:                   ;
jumpc193:                   ;
jumpc194:                   ;
jumpc195:                   ;
jumpc196:                   ;
jumpc197:                   ;
jumpc198:                   ;
jumpc199:                   ;
jumpc200:                   ;
jumpc201:                   ;
jumpc202:                   ;
jumpc203:                   ;
jumpc204:                   ;
jumpc205:                   ;
jumpc206:                   ;
jumpc207:                   ;
jumpc208:                   ;
jumpc209:                   ;
jumpc210:                   ;
jumpc211:                   ;
jumpc212:                   ;
jumpc213:                   ;
jumpc214:                   ;
jumpc215:                   ;
jumpc216:                   ;
jumpc217:                   ;
jumpc218:                   ;
jumpc219:                   ;
jumpc220:                   ;
jumpc221:                   ;
jumpc222:                   ;
jumpc223:                   ;
jumpc224:                   ;
jumpc225:                   ;
jumpc226:                   ;
jumpc227:                   ;
jumpc228:                   ;
jumpc229:                   ;
jumpc230:                   ;
jumpc231:                   ;
jumpc232:                   ;
jumpc233:                   ;
jumpc234:                   ;
jumpc235:                   ;
jumpc236:                   ;
jumpc237:                   ;
jumpc238:                   ;
jumpc239:                   ;
jumpc240:                   ;
jumpc241:                   ;
jumpc242:                   ;
jumpc243:                   ;
jumpc244:                   ;
jumpc245:                   ;
jumpc246:                   ;
jumpc247:                   ;
jumpc248:                   ;
jumpc249:                   ;
jumpc250:                   ;
jumpc251:                   ;
jumpc252:                   ;
jumpc253:                   ;
jumpc254:                   ;
jumpc255:                   ;

 ; alapertelmezes az hogy a fonetikus kod megegyezik a normal koddal
;
nodif:
                mov    phonout[di],ah
                inc    si
                inc    di
                inc    phonlgt
                jmp    endtest
;


jumpc067:                   ;C
jumpc099:                   ;c
                lea    bx,textout[si]
                mov    di,offset ctar        ; c betukombinaciok szotara
                mov    lszo,di
                jmp    hkulcsfind

jumpc107:                   ;k
jumpc075:                   ;K
                lea    bx,textout[si]
                mov    di,offset ktar        ; k betukombinaciok szotara
                mov    lszo,di
                jmp    hkulcsfind

jumpc086:                   ;V
jumpc118:                   ;v
                lea    bx,textout[si]
                mov    di,offset vtar        ; v betukombinaciok szotara
                mov    lszo,di
                jmp    hkulcsfind
;

jumpc083:                   ;S
jumpc115:                   ;s
                lea    bx,textout[si]
                mov    di,offset star        ; s betukombinaciok szotara
                mov    lszo,di
                jmp    hkulcsfind
;
jumpc090:                   ;Z
jumpc122:                   ;z
                lea    bx,textout[si]
                mov    di,offset ztar        ; z betukombinaciok szotara
                mov    lszo,di
                jmp    hkulcsfind
;
jumpc084:                   ;T
jumpc116:                   ;t
                lea    bx,textout[si]
                mov    di,offset ttar        ; t betukombinaciok szotara
                mov    lszo,di
                jmp    hkulcsfind
;
jumpc078:                   ;N
jumpc110:                   ;n
                lea    bx,textout[si]
                mov    di,offset ntar        ; n betukombinaciok szotara
                mov    lszo,di
                jmp    hkulcsfind
;
jumpc076:                   ;L
jumpc108:                   ;l
                lea    bx,textout[si]
                mov    di,offset ltar        ; l betukombinaciok szotara
                mov    lszo,di
                jmp    hkulcsfind
;
jumpc071:                   ;G
jumpc103:                   ;g
                lea    bx,textout[si]
                mov    di,offset gtar        ; g betukombinaciok szotara
                mov    lszo,di
                jmp    hkulcsfind
;
jumpc068:                   ;D
jumpc100:                   ;d
                lea    bx,textout[si]
                mov    di,offset dtar        ; d betukombinaciok szotara
                mov    lszo,di
                jmp    hkulcsfind
;

jumpc045:                   ;mn        -
                lea    bx,textout[si]
                mov    di,offset mntar        ; d betukombinaciok szotara
                mov    lszo,di
                jmp    hkulcsfind

;
hkulcsfind:
nextkulcs:
                mov    cx,0
                mov    cl,byte ptr [di]
                jcxz   tarvege
                mov    si,bx       ; az aktualis karakter cime a textout -ban
                inc    di          ; kulcs relativ kezdocim
                cld
                repe   cmpsb
                je     hangfindj
                mov    ax,30       ; elokeszites a kov. kulcshoz
                add    lszo,ax
                mov    di,lszo
                jmp    nextkulcs
hangfindj:      jmp    hangfind

tarvege:
                mov    ax,sax
                mov    si,ssi
                mov    di,sdi
                jmp    nodif
         jmp    tarvege


hangfind:
                mov    si,lszo              ; kulcs relativ kezdocim
                mov    cx,0
                mov    cl,byte ptr [si]     ; a kulcs hossza
                add    ssi,cx               ; atugorjuk a kulcsot textout -ban
                add    si,15
                mov    cl,byte ptr [si]     ; hang hossz
                mov    sisave,si
                jcxz   tarvege      ; digital

                inc    si                   ; hang kezdocim
                mov    di,sdi               ; aktualis cim phonsout -ban
                add    sdi,cx
                add    phonlgt,cl
                lea    di,phonout[di]
                cld
                rep movsb
                mov    si,ssi
                mov    di,sdi
                jmp    endtest


ciklcvjmp:      jmp    ciklcv

endtest:
                mov    bx,0
                mov    bl,textlgt
                cmp    si,bx
                jbe    ciklcvjmp

over:
         mov bl,' '
         mov phonout[di],bl
         ret
convert  endp

l9esith  proc

              cli
              push    ax
              push    bx
              push    cx
              push    dx
              push    di
              push    si
              push    ds
              push    es

              pushf
              call    cs:old_keyboard_int        ; eloszor hivjuk az eredeti rutint
              cli

              assume  ds:rom_bios_data
              mov     bx,rom_bios_data
              mov     ds,bx
              mov     ax,cs:stail
              mov     cx,cs:shead
              mov     tail,ax                    ; a bevitt karakter vizsgalata
              mov     head,cx

outug:
             cli
             pop        es
             pop        ds
             pop        si
             pop        di
             pop        dx
             pop        cx
             pop        bx
             pop        ax
             mov    al,20h
             out    20h,al            ; interrupt vege

         pop ax
         pop ax                       ; nem iret -el lepunk ki
         popf

         mov ax,cs:sssave
         mov ss,ax
         mov ax,cs:essave
         mov es,ax
         mov ax,cs:spsave
         mov sp,ax
         mov bx,cs:joutit
         sti

         jmp bx

l9esith  endp


main     proc far
; *****************************************************************

         push ds
         sub  ax,ax
         push ax
         ;
         mov cs:pspseg,ds

         ;




         mov  ax,dseg
         mov  ds,ax
         mov  es,ax
         assume ds:dseg,es:dseg

;;;;;;;;;;;;;;;;;;;;;;     most nem a kartyara irunk, hanem a printer portra

;       push ds
;       mov  ax,portseg
;       mov  ds,ax
;       mov  ax,portcim                    ; portcim beallitasa
;       pop  ds                            ; a printerre irunk !
;       mov  writec,ax

       ; reset

cimbeall:
        mov al,1
        mov dx,writec
        add dx,6             ;   226
        out dx,al
        mov cx,100
micr:   loop micr
        mov al,0
        out dx,al
        mov cx,1000
micr2:  loop micr2
        mov dx,writec
        add dx,0ah           ;   22a
        in  al,dx
        cmp al,0aah
        jne stathiba
        mov  dx,writec
        add  dx,0ch          ;  22c
        mov  al,0d1h
        out  dx,al           ;            speaker on
        jmp  cim1ok
;;;;;;;;;;;;;;;;;;;;;;

       ;                   hianyzik a kartya   -   hibauzenet

stathiba:
         add writec,10h
         cmp writec,260h
         jbe cimbeall


         cls
         prompt messcop
         rclf
         rclf
         rclf
         prompt karderr
         rclf
         ret

cim1ok:

cim2ok:

         mov dx,writec
;        mov al,128                          ; nulla feszultsegszint kiiras
;        out dx,al


         rclf
         prompt messcop
         mov dx,writec
;        mov al,128
;        out dx,al

;                            sebesseg meghatarozas



         mov ah,0
         mov al,timersz
         mov speed,ax

         sub ax,speedmn
         add ax,speedpl
         mov speed,ax

         mov ax,4                  ;    timer hasznalata eseten
         mov speedstp,ax           ;    intonaciohoz  delta-timer




;          jmp  nodirect
           jmp  restart
exitjump:  jmp  exit



; ------------------------------------
nodirect:
          call lld           ; a hangfile-t direkt modon irjuk a programba !
          jcxz exitjump
          jc   exitjump
;         call loadhang
; ------------------------------------

restart:
         cmp   polvasva,0
         jnz   exitjump

         assume ds:dseg,cs:cseg,ss:sseg

         push  ds                  ; a parameter blokk ellenorzese
         mov   di,offset textlgt
         mov   ds,cs:pspseg
         mov   si,80h
         cmp   byte ptr [si],0
         jz    nopars              ; szoveg beolvasasa ha van
         cmp   byte ptr [si+2],'*'
         jnz   kodtest
         mov   cx,0
         mov   cl,[si]
         inc   cx
         cld
         rep movsb
         pop   ds
         mov   polvasva,1
         jmp   parcon



kodtest:
         cmp   byte ptr [si+2],'.'         ; ezzel aktivaljuk a kodmegjelenitest
         jnz   nopars
         pop   ds
         cls
         prompt messcop
         mov   dl,0ffh
         mov   ah,06h
kodki:   int   21h                         ; a kod lekerdezese ugy tortenik
         jz    kodki                       ; olvas .
         cmp   al,'√'                      ; majd beirjuk,hogy ALT 195
         jnz   rosszk
         call  kodproc
         call  kodin
rosszk:  jmp elegvolt

nopars:
         cmp   byte ptr [si+2],'+'
         jnz   noplussz
         mov   bl,byte ptr [si+3]
         pop   ds
         mov   ax,0
         sub   ax,speed
         shr   ax,1
         shr   ax,1
         shr   ax,1
         sub   bl,30h
         mul   bl
         mov   speedpl,ax
         call  rewrite
         jmp   elegvolt


restartj: jmp restart

noplussz: cmp   byte ptr [si+2],'-'
         jnz   noadj
         mov   bl,byte ptr [si+3]
         pop   ds
         mov   ax,0
         sub   ax,speed
         shr   ax,1
         shr   ax,1
         shr   ax,1
         sub   bl,30h
         mul   bl
         mov   speedmn,ax
         call  rewrite
         jmp   elegvolt

noadj:
         pop    ds
         lea    dx,term
         mov    ah,9
         int    21h
         call textin

parcon:  mov cx,0
         mov cl,textlgt
         jcxz exit

; phonetic conversion


         mov  phnext,0
         mov  phonlgt,0
         call convert

a1:      call phonsout

exit:
        cmp   polvasva,1
        jz    elegvolt
        mov    ah,0bh               ; standard input test
        int    21h                  ; (az input szovegfilet Ctrl C -vel
        cmp    al,0                 ; kell lezarni)
        jnz    restartj


elegvolt: mov dx,writec
;        mov al,0
;        out dx,al


         ret
main     endp

kodin    proc
         mov   dl,0ffh
         mov   ah,06h
retry1:  int   21h
         jz    retry1
         cmp   al,'√'
         jnz   nokod
         mov   dl,0ffh
         mov   ah,06h
retry2:  int   21h
         jz    retry2
         cmp   al,'='
         jnz   nokod
         mov   dl,0ffh
         mov   ah,06h
retry3:  int   21h
         jz    retry3
         cmp   al,''
         jnz   nokod
         valasz fkodin
         mov   ax,0
         mov   al,kodhossz
         mov   cx,ax
         mov   si,0
ckod:    mov   ax,si
         add   felhkod[si],al
         inc   si
         loop  ckod
         mov   al,'$'
         mov   felhkod[si],al
         rclf
         rclf
         call rewrite
nokod:
         ret
kodin    endp

hexa     proc near
         mov dh,al
         shr al,1
         shr al,1
         shr al,1
         shr al,1
         call alakit
         mov al,dh
         and al,0fh
         call alakit
         ret
hexa     endp

spacep   proc near
         mov dl,20h
         mov ah,6
         int 21h
         ret
spacep   endp

alakit   proc
         add al,30h
         cmp al,39h
         jbe alakit1
         add al,7
alakit1: mov dl,al
         mov ah,6
         int 21h
         ret
alakit   endp

printout proc
      push ax          ; ax - ben van a kiirando szo
      mov al,ah
      call hexa
      pop  ax
      call hexa
      call spacep
      ret
printout endp




rewrite  proc
      mov  ah,3           ; disk write
      mov  al,1           ; no of recs
      mov  dl,0           ; a:
      mov  dh,1           ; double sided              itt visszairjuk az uj
      mov  ch,0           ; start track                     kodot
      mov  cl,5           ; starting sector
      lea  bx,portc       ; es:bx puffer address
      int  13h
      ret
rewrite  endp


kodproc  proc
         rclf
         mov   si,0
         mov   ax,0
         mov   al,kodhossz
         mov   cx,ax
dekod:   mov   ax,si
         sub   felhkod[si],al
         inc   si
         loop  dekod
         prompt felhkod
         rclf
         ret
         db 2eh
kodproc  endp

del   proc near
ujat: mov  ax,2c00h
      int  21h
      cmp  dl,48
      ja   ujat
      mov  clock,dl
      add  clock,50
back: mov  ax,2c00h
      int  21h
      cmp  dl,clock
      jbe  back
      ret
del   endp

textin   proc
         lea    dx,bufsize
         mov    ah,10            ;valasz beolvasasa
         int    21h
         mov    cx,0
         mov    cl,num
         mov    textlgt,cl
         jcxz   cxzero
         lea    si,bufr
         lea    di,textout
         cld                     ;valasz atpakolasa
         rep movsb
         appnd zar,textlgt       ; zaro space
cxzero:  ret
textin   endp


lld    proc
       lea   dx,filnam
       mov   ax,3d00h             ; open file for reading
       int   21h
       jc    error
       mov   bx,ax
       mov   cx,0
       mov   dx,0
       mov   ax,4200h             ; set file pointer
       int   21h
       lea   dx,bufrr
       mov   cx,63000
       mov   ah,3fh               ; read to the buffer
       int   21h
       mov   buffl,ax             ; no of caracters read
       mov   ah,3eh               ; close the file
       int   21h

       mov si,0
       mov cx,60000
       mov dx,portc
       ret

error:   lea   dx,crerr
         mov   ah,9
         int   21h

        lea    dx,term
        mov    ah,9
        int    21h


nofilen: ret

lld     endp


loadhang proc
         push  es
         push  ds
         push  ds
         pop   es
         mov   ax,hangds
         mov   ds,ax
         assume ds:hangds


       lea   dx,fname
       mov   ax,3d00h             ; open file for reading
       int   21h
       jc    fnerror
       mov   bx,ax
       mov   cx,0
       mov   dx,0
       mov   ax,4200h             ; set file pointer
       int   21h
       lea   dx,hangbuf

       mov   cx,63000
       mov   ah,3fh               ; read to the buffer
       int   21h
       mov   hanglgt,ax           ; no of caracters read
;
       mov   es:maxdi,ax
       mov   si,ax
       sub   si,2
       mov   ah,hangbuf[si]
       mov   es:timer,ah          ;   rovidebb file eseten atpaakoljuk a
       inc   si                   ;   a timert es a tomind -t
       mov   ah,hangbuf[si]
       mov   es:tomind,ah
;

       mov   ah,3eh               ; close the file
       int   21h

fnerror: pop   ds
         assume ds:dseg
         pop   es

         mov   ah,timer        ;  timer ellenorzes
         cmp   ah,timer1
         je    timerok
         cmp   ah,timer2
         je    timerok
         cmp   ah,timer3
         je    timerok
         mov   ah,timer2        ;  ha sebesseg nem ok akkor 8 kHz
         mov   timer,ah
timerok:
;
; itt ellenorizzuk,hogy nem tomoritett file-t olvastunk-e be. Ha igen akkor
; dekompressalas !

       cmp tomind,240
       jne  nemtom
       cmp  maxdi,7800
       jae  nemtom
        push ds
        mov   ax,hangds
        mov   ds,ax
        push  es
        mov   ax,tomds
        mov   es,ax
        assume ds:hangds,es:tomds
       call fixing          ;   attoltes a tomds-be
       call decompr         ;   dekompressalas a tomds-bîl a hangseg -be
       call simitas         ;   na es a simitas
         pop   es
         pop   ds
         assume es:dseg,ds:dseg

nemtom:
       mov  tomind,0

;
;

         ret
loadhang endp


fixing   proc
         mov   cx,hanglgt           ;     a hangbuf-bol a tombuf-ba
         mov   di,0
         lea   si,hangbuf
         cld
         rep movsb
         ret
fixing   endp


decompr       proc                         ;     es:tomds[di] ---> bufrr[si]
                                           ;     di a kovetkezo szakaszra mutat,
                                           ;     si szinten
                                           ;     es beallitva
               mov   di,0
               lea   si,hangbuf
deccikl:
               mov   al,es:[di]
               mov   posszam,al
               inc   di
               mov   al,es:[di]
               mov   negszam,al

               mov   cx,30
decompint:
               call  decsub
               loop  decompint

               cmp   di,hanglgt
               jae   deckesz
               jmp   deccikl
deckesz:
               lea   di,hangbuf
               sub   si,di
               mov   hanglgt,si
               sub   hanglgt,240
               ret
decompr        endp


decsub      proc
               inc   di
               mov   ah,es:[di]

dec1:          test  ah,tom1
               jz    posdec1
               mov   al,negszam
          ;    mov   hangbuf[si],al
               mov   [si],al
               jmp   dec2
posdec1:       mov   al,posszam
               mov   [si],al

dec2:          inc   si
               test  ah,tom2
               jz    posdec2
               mov   al,negszam
               mov   [si],al
               jmp   dec3
posdec2:       mov   al,posszam
               mov   [si],al

dec3:          inc   si
               test  ah,tom3
               jz    posdec3
               mov   al,negszam
               mov   [si],al
               jmp   dec4
posdec3:       mov   al,posszam
               mov   [si],al

dec4:          inc   si
               test  ah,tom4
               jz    posdec4
               mov   al,negszam
               mov   [si],al
               jmp   dec5
posdec4:       mov   al,posszam
               mov   [si],al

dec5:          inc   si
               test  ah,tom5
               jz    posdec5
               mov   al,negszam
               mov   [si],al
               jmp   dec6
posdec5:       mov   al,posszam
               mov   [si],al

dec6:          inc   si
               test  ah,tom6
               jz    posdec6
               mov   al,negszam
               mov   [si],al
               jmp   dec7
posdec6:       mov   al,posszam
               mov   [si],al

dec7:          inc   si
               test  ah,tom7
               jz    posdec7
               mov   al,negszam
               mov   [si],al
               jmp   dec8
posdec7:       mov   al,posszam
               mov   [si],al

dec8:          inc   si
               test  ah,tom8
               jz    posdec8
               mov   al,negszam
               mov   [si],al
               jmp   decout
posdec8:       mov   al,posszam
               mov   [si],al
decout:        inc   si
            ret
decsub      endp


simitas         proc

hszin:

                lea si,hangbuf
                inc si
                lea di,hangbuf
                mov cx,59998
szinez:
                mov  ax,0
                mov  bx,0
                push di
           ;    mov  al,hangbuf[di]
                mov  al,[di]
                add  bx,ax
                inc  di
                mov  al,[di]
                add  bx,ax

                shr  bx,1
                mov  al,bl
                mov  [si],al
                pop  di
                inc  di
                inc  si
                loop szinez


                mov si,0
                mov di,1
                mov cx,59998


                jmp  simout             ;  lefuto elt nem bantjuk


szinez2:                                 ; lefuto el simitasa
                mov  ax,0
                mov  bx,0
                push di
                mov  al,[di]
                add  bx,ax
                dec  di
                mov  al,[di]
                add  bx,ax
                shr  bx,1
                mov  al,bl
                mov  [si],al
                pop  di
                inc  di
                inc  si
                loop szinez2

simout:         ret
simitas         endp



szamsout proc
         mov phnext,0
ciklph2: mov si,phnext
         mov ax,0
         mov al,phonout[si]
backph2: shl ax,1
         shl ax,1
         mov si,ax
         mov ax,c000c[si]

          mov bx,htblptr
          mov [bx],ax             ; start
         inc si
         inc si
          inc bx
          inc bx
         mov ax,c000c[si]
          mov [bx],ax              ; hossz
           inc bx
           inc bx
           mov ax,speed
           mov [bx],ax               ; speed=bxcont a hang-ban
           inc bx
           inc bx
           mov htblptr,bx

      ;  call hang

         inc phnext
         mov ax,0
         mov al,phonlgt
         cmp ax,phnext
         ja  ciklph2
         push    ds
         mov     cx,seg szamds
         mov     ds,cx
         assume  ds:szamds
         mov     string1,0
         pop     ds
         assume  ds:dseg
         mov     spind,1
         ret
szamsout endp



phonsout proc
         mov phnext,0
          lea cx,htbl                 ; htblptr a tabla kovetkezo ures
          mov htblptr,cx              ; helyere fog mutatni
         push    ds
         mov     cx,seg szamds
         mov     ds,cx
         assume  ds:szamds
         mov     string1,0
         pop     ds
         assume  ds:dseg

ciklph:  mov si,phnext

 ;  az olvasi -bîl †tvÇve
 ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;

         cmp phonout[si+3],'.'
         jz  pontlessz
         cmp pontkov,0
         jz  veszteszt
pontlessz:
         inc pontkov
         inc pontkov
         inc pontkov
         inc pontkov
         cmp pontkov,12
         jbe veszteszt
         mov pontkov,0
         mov ejtes,25

veszteszt:
         cmp phonout[si+3],','
         jz  veszlessz
         cmp veszkov,0
         jz  inton
veszlessz:
         inc veszkov
         inc veszkov
         inc veszkov
         inc veszkov
     ;   inc veszkov
     ;   cmp veszkov,15
         cmp veszkov,12
         jbe inton
         mov veszkov,0
         mov ejtes,25

inton:
         cmp ejtes,1
         jb  nemejt
         dec ejtes
nemejt:

;         ; ez volt a hanlejtÇs nÇlkÅli verzi¢ban !
;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
;
;         cmp phonout[si+3],'.'
;         jz  pontlessz
;         cmp pontkov,0
;         jz  veszteszt
;pontlessz:
;         mov ax,speedstp
;         add pontkov,ax
;         add ax,speedstp
;         add ax,speedstp
;         cmp pontkov,ax
;         jbe veszteszt
;         mov pontkov,0
;         mov ejtes,25
;
;veszteszt:
;         cmp phonout[si+3],','
;         jz  veszlessz
;         cmp veszkov,0
;         jz  inton
;veszlessz:
;         mov ax,speedstp
;         add veszkov,ax
;         add ax,speedstp
;         cmp veszkov,ax
;         jbe inton
;         mov veszkov,0
;         mov ejtes,25
;
;inton:
;         cmp ejtes,1
;         jb  nemejt
;         dec ejtes
;nemejt:



         mov ax,0
         mov al,phonout[si]

         jmp szamtest

backph:  shl ax,1
         shl ax,1
         mov si,ax
         mov ax,c000c[si]

      ;   mov start,ax
          mov bx,htblptr
          mov [bx],ax                 ; start
         inc si
         inc si
          inc bx
          inc bx
         mov ax,c000c[si]
      ;   mov hossz,ax
          mov [bx],ax                 ; hossz
           inc bx
           inc bx
           mov ax,speed

 ;;;;;;;;  sub ax,12

           add ax,veszkov
           sub ax,pontkov

 ;;;;;;;;  add ax,ejtes              ;  folyamatos hanglejtes

           mov [bx],ax               ;  speed=bxcont a hang-ban
           inc bx
           inc bx
           mov htblptr,bx

      ;  call hang

         inc phnext
         mov ax,0
         mov al,phonlgt
         cmp ax,phnext
         ja  atugras2

          jmp atugras1
atugras2: jmp ciklphjump
atugras1:
         cli
         mov cs:sssave,ss
         mov cs:spsave,sp
         mov cs:dssave,ds
         mov cs:essave,es
                push    ds
              assume  ds:rom_bios_data
              mov     bx,rom_bios_data
              mov     ds,bx
              mov     bx,tail
              mov     cs:stail,bx
              mov     bx,head
              mov     cs:shead,bx
                assume  ds:interrupts
                mov     ax,interrupts
                mov     ds,ax
                mov     ax,word ptr keyboard_int
                mov     word ptr cs:old_keyboard_int,ax
                mov     ax,word ptr keyboard_int[2]
                mov     word ptr cs:old_keyboard_int[2],ax
                push    ds
                push    cs
                pop     ds
                mov     ax,offset l9esith
                pop     ds
                mov     word ptr keyboard_int,ax
                mov     word ptr keyboard_int[2],cs
                pop     ds
                mov     ax,offset backout
                mov     cs:joutit,ax
                sti

          call hang                       ;  modositott hang

backout:        cli
                assume  ds:interrupts
                mov     ax,interrupts
                mov     ds,ax
                mov     ax,word ptr cs:old_keyboard_int
                mov     word ptr keyboard_int,ax
                mov     ax,word ptr cs:old_keyboard_int[2]
                mov     word ptr keyboard_int[2],ax
                sti

         mov ax,dseg
         mov ds,ax
         mov es,ax
         assume ds:dseg,es:dseg
         ret

ciklphjump: jmp ciklph


szamtest:                          ; ellenorizzuk, hogy a szovegben
                                   ; kovetkezo karakter szam-e
         mov     cx,seg szamds
         mov     es,cx
         assume  es:szamds
         cmp     al,39h
         ja      noszam
         cmp     al,30h
         jb      noszam
         jmp     szamchj
noszam:  cmp     al,'.'
         jnz     nopont
         cmp     szamind,0           ; ha szam volt elotte
         jz      szamchj

nopont:  cmp     al,'/'
         jnz     szolsz
         cmp     szamind,0           ; szam ?
         jz      szamchj
         jmp     scrszojm


szolsz:
         cmp     szamds:string1,0     ; ha az aktualis karakter nem szam, akkor
         ja      cmain2j              ; megnezzuk, hogy volt-e szam ezt megelozoen
         cmp     al,' '
         jnz     scrszoj
         mov     spind,0              ; space
         jmp     jback
szamchj: jmp     szamch
cmain2j: jmp    cmain2



scrszoj:
         cmp     al,'#'
         jnz     testmjump
         jmp     parancst
testmjump:
         jmp     testmnsz
;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;; parancs teszt ;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
parancst:
         cmp    phonout[si+1],'v'
         jne    testmjump            ;    ismeretlen parancs

         push   cx
         push   di
         push   ax
         push   si

         mov    keses,0
         mov    num,0
         push   si
         add    si,2
hote:    cmp    phonout[si],' '
         je     hosszok
         inc    num
         inc    si
         jmp    hote
hosszok:
         pop    si
         mov    mult10,1
         mov    cx,10
         lea    si,phonout[si+1]       ;     ez mÇg a v -jelre mutat
         mov    bx,0
         mov    bl,num
b20:     mov    al,[si+bx]
         and    ax,000fh
         mul    mult10
         add    keses,ax
         mov    ax,mult10
         mul    cx
         mov    mult10,ax
         dec    bx
         jnz    b20


         pop    si
         pop    ax

         push   si
         mov    cx,0
         mov    cl,num
         add    si,cx
         inc    si
toltes:  mov    phonout[si],al
         dec    si
         loop   toltes
         pop    si

         pop    cx
         pop    di
         jmp    testmnsz
;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;


testmnsz:
         cmp     al,'-'
         jnz     testplsz
         ;                             ; itt kellene megnezni hogy szam
         ;                              ; kovetkezik e
         mov     bl,phonout[si+1]
         cmp     bl,39h
         ja      kijar
         cmp     bl,30h
         jb      kijar
         mov     spind,0
         jmp     testsp

testplsz: cmp     al,'+'
         jnz     testegyn
         mov     spind,0
         jmp     testsp

testegyn: cmp     al,'='
         jnz     testszz
         mov     spind,0
         jmp     testsp

testszz: cmp     al,'%'
         jnz     testdol
         mov     spind,0
         jmp     testsp

testdol: cmp     al,'$'
         jnz     testsp
         mov     spind,0

testsp:  cmp     spind,0
         jz      scrszojm
kijar:   mov     spind,1              ; no space
         jmp     jback
scrszojm:
         jmp     scrszo

cmain2:  mov     sax,ax           ; ha igen, akkor felolvassuk
         call    main2
         mov    ax,dseg
         mov    ds,ax
         mov    es,ax
         assume ds:dseg,es:dseg

         mov    phnext,0
         mov    phonlgt,0
         call   convert

         call   szamsout

         movstr phons,phonlgt
         mov     cx,phnexts
         mov     phnext,cx

         mov     ax,0
         mov     al,phonlgt
         cmp     ax,phnext
         jbe     backoutj

         mov     ax,sax
         jmp     ciklph

jback:
         mov     szamind,1
         jmp     backph

backoutj: jmp     backout


szamch:
         mov     szamind,0
         mov     cx,0
         push    es
         push    ds

         push    es
         pop     ds
         assume  ds:szamds
         inc     string1
         mov     cl,string1
         mov     di,cx
         mov     string1[di],al
         pop     ds
         pop     es
         assume  ds:dseg
         inc     phnext

         jmp     ciklph            ; ha szam akkor atpakoltuk, es most nezzuk

                                   ; a kovetkezot
 ; end of szamtest

phonsout endp


; itt kovetkezik a szotar kezelo programresz
; inditva a szamtest -bol ha a soron kovetkezo karakter
; space es ezt megelozoen nem szam volt

scrszo:
          mov    spind,1
          mov    sax,ax
          mov    lszo,0
          cmp    al,3eh
          jb     sztr             ;     + - = % $
          mov    lszo,120
          jmp    sztr

sztr:     push  es
          assume es:szamds,ds:dseg

          lea   bx,phonout[si]                    ; bx az aktualis szovegreszre
          push  ds                                ; mutat
          push  es
          pop   ds
          assume ds:szamds
          mov   di,offset szotar
          pop   ds
          assume ds:dseg
          add   di,lszo
          mov   lszo,di

nextszo:  mov   cx,0
          push  ds
          push  es
          pop   ds
          assume ds:szamds
          mov   cl,byte ptr [di]           ; cl -  a kulcs hossza
          pop   ds
          assume ds:dseg
          jcxz  notfind
          mov   si,bx
          inc   di
          cld
          repe  cmpsb
          je    kulcsfind
          mov   ax,0
          mov   al,30
          add   lszo,ax
          mov   di,lszo
          jmp   nextszo

notfind:  mov   ax,sax
          pop   es
          assume es:szamds
          mov   szamind,0
          jmp   backph

kulcsfind:
          push  es
          push  ds
          pop   es
          assume es:dseg,ds:dseg
          movstr phonlgt,phons
          pop   es
          assume es:szamds
          mov   di,lszo
          mov   cx,0
          push  ds
          push  es
          pop   ds
          assume ds:szamds
          mov   cl,byte ptr [di]
          pop   ds
          assume ds:dseg
          add   phnext,cx
          mov   ax,phnext              ; az aktulalis allapot elmentese
          mov   phnexts,ax

          add   di,15

          mov    cx,0
          push  ds
          push  es
          pop   ds
          assume ds:szamds, es:szamds
          mov    cl,byte ptr [di]
          pop   ds
          assume ds:dseg
        mov    si,di                   ; a hosszat is atirjuk
        jcxz   nincsmit                ; hangfile !

        ;
        ;   ide tesszuk be annak az esetnek a vizsgalatat, hogy direkt
        ;   hangfile-e. A szovegben a file nevet egy   &  jelnek kell
        ;   megelozni. A szotarban a & kulcshoz tartozo fonetikus
        ;   megfelelo hossza = FF
        ;
        cmp    cl,0ffh
        jne    nodfile
        push   si
        push   di
        mov    si,bx
        inc    si
        mov    cx,0          ;    ha igaz si a & jel utani karakterre mutat
        inc    di            ;    meg nem tudjuk a hosszat
nevpack:
        mov    al,byte ptr [si]
        cmp    al,' '
        je     keszpack
        mov    es:byte ptr [di],al
        inc    cx
        inc    si
        inc    di
        cmp    cx,11
        jae    keszpack
        jmp    nevpack
keszpack:

        mov    al,' '
        push   cx
kitlts:
        cmp    cx,11
        jae    kitoltv
        mov    es:byte ptr [di],al
        inc    di
        inc    cx
        jmp    kitlts

kitoltv:
        pop    cx
        pop    di
        pop    si
        add    phnext,cx                    ;    at kellene ugrani a nevet
        dec    phnext

        jmp    dirfile

        ;
        ;

nodfile:
        inc    cx
        lea    di,textlgt
        cld
        push   es
        push   ds

        push   ds
        push   es
        pop    ds
        pop    es

        rep movsb                     ; ha nem hangfile volt akkor atirjuk
                                      ; a fonetikus megfelelot
        pop    ds
        pop    es

        jmp    atirva



dirfile:
nincsmit:

                                   ; itt kell betolteni es kiirni a kulcsnak
                                   ; megfelelo hangfilet

         cli
         mov cs:sssave,ss
         mov cs:spsave,sp
         mov cs:dssave,ds
         mov cs:essave,es
                push    ds
              assume  ds:rom_bios_data
              mov     bx,rom_bios_data
              mov     ds,bx
              mov     bx,tail
              mov     cs:stail,bx
              mov     bx,head
              mov     cs:shead,bx
                assume  ds:interrupts
                mov     ax,interrupts
                mov     ds,ax
                mov     ax,word ptr keyboard_int
                mov     word ptr cs:old_keyboard_int,ax
                mov     ax,word ptr keyboard_int[2]
                mov     word ptr cs:old_keyboard_int[2],ax
                push    ds
                push    cs
                pop     ds
                mov     ax,offset l9esith
                pop     ds
                mov     word ptr keyboard_int,ax
                mov     word ptr keyboard_int[2],cs
                pop     ds
                mov     ax,offset backout2
                mov     cs:joutit,ax
                sti


         push es
         mov  ax,hangds
         mov  es,ax
         assume es:hangds

         push ds

         mov  ax,szamds
         mov  ds,ax
         assume ds:szamds
         mov  cx,14                ; file nev atmasolas
         lea  di,es:fname
         inc  si                   ; atugrottuk a 0 -t
         cld
         rep  movsb

         pop  ds
         assume  ds:dseg



          call hang                       ;  modositott hang
          call loadhang





;        call hang             ; hangbuffer kiuritese
;
;        call loadhang


         mov si,0
         mov cx,es:hanglgt
         mov dx,writec

         mov al,98h
         out 43h,al
         mov al,0
         out 42h,al            ;   a timer felprogramozasa
         in  al,61h
         or  al,01h
         out 61h,al

hangki:   mov al,es:hangbuf[si]

          call checkst
          out dx,al
          ; * ;;;
          mov ax,ax            ;   kesleltetes
          mov ax,ax            ;   kesleltetes
          mov ax,ax            ;   kesleltetes
          mov ax,ax            ;   kesleltetes
          mov ax,ax            ;   kesleltetes
          mov ax,ax            ;   kesleltetes
          mov ax,ax            ;   kesleltetes
          mov ax,ax            ;   kesleltetes
          mov ax,ax            ;   kesleltetes
          ; * ;;;
          inc si


varunk:   in  al,42h
          cmp al,timer          ;    8.5 khz =  73h
          ja  varunk
          mov al,0
          out 42h,al

          loop hangki


         pop  es
         assume es:szamds
         mov    ax,32                      ; space a hangfile utan
         mov    sax,ax

backout2:       cli
                push    ds
                assume  ds:interrupts
                mov     ax,interrupts
                mov     ds,ax
                mov     ax,word ptr cs:old_keyboard_int
                mov     word ptr keyboard_int,ax
                mov     ax,word ptr cs:old_keyboard_int[2]
                mov     word ptr keyboard_int[2],ax
                pop     ds
                sti
        jmp   notfind




atirva:

          mov   phnext,0
          mov   phonlgt,0

          call  convert

          call  szamsout

          push  ds
          pop   es
          assume ds:dseg,es:dseg
          movstr phons,phonlgt
          mov   ax,phnexts             ; allapot visszaallitas
          mov   phnext,ax

          mov   ax,0
          mov   al,phonlgt
          cmp   ax,phnext
          ja    ciklphjmp
          mov   ax,sax
          pop   es
          assume es:szamds
          jmp   backout
ciklphjmp:
          pop   es
          assume es:szamds
          mov   si,phnext
          cmp   phonout[si-1],' '
          jnz   nospend
          mov   spind,0
nospend:  mov   ax,sax
          jmp   ciklph

;
;

checkst  proc
          push ax
       ;  push dx
          mov  dx,writec
          add  dx,0ch            ;     22c
megne1:   in   al,dx
          and  al,80h
          cmp  al,0
          jnz  megne1
          mov  al,10h
          out  dx,al
       ;  mov  dx,writec
       ;  add  dx,0ch            ;     22c
megne2:   in   al,dx
          and  al,80h
          cmp  al,0
          jnz  megne2
       ;  pop dx
          pop ax
          ret
checkst   endp

;
hang     proc
;;;;;;;;;;;;;;
            push es
            mov  ax,hangds
            mov  es,ax
            mov  di,keses
            mov  fej,di
            mov  farok,0
         lea  ax,htbl
         mov  htblptrn,ax
         cmp  htblptr,ax
         jbe  nincshangj
         jmp  ujhangstart
nincshangj:
         jmp  nincshang

ujhangstart:
;;;;
         mov   bx,htblptrn
         mov   si,word ptr [bx]   ; start
         inc   bx
         inc   bx
         mov   cx,word ptr [bx]   ; hossz
         inc   bx
         inc   bx
         mov   ax,word ptr [bx]   ; speed
         inc   bx
         inc   bx
         mov   htblptrn,bx
         mov   bx,ax

;;;;
         mov ax,0
         mov dx,writec

         mov al,98h
         out 43h,al
         mov al,0
         out 42h,al            ;   a timer felprogramozasa
         in  al,61h
         or  al,01h
         out 61h,al

loopout: mov al,bufrr[si]      ; start to speak

ujvisszh:
         mov di,farok
         mov ah,es:hangbuf[di]
         shr ah,1
         sub ah,64
         jc  neg_viszh
         add al,ah
         jc  tul_poz
         jmp noviszh
neg_viszh:
         add al,ah
         jnc tul_neg
         jmp noviszh
tul_poz:
         mov al,0ffh
         jmp noviszh
tul_neg: mov al,0

noviszh:
         mov di,fej
         mov es:hangbuf[di],al

         call checkst

         out dx,al
         call keslelts
noviszhh:

;
;
;

         inc si

         inc fej
         mov di,fej
         cmp di,keses
         jbe fejok
         mov fej,0
fejok:   inc farok
         mov di,farok
         cmp di,keses
         jbe farokok
         mov farok,0
farokok:

delay:   in  al,42h
         cmp al,bl             ;     8 khz  =  6ah
         ja  delay
         mov al,0
         out 42h,al
         loop loopout

         mov   bx,htblptrn
         cmp   bx,htblptr
         jae   pkilep
         jmp   ujhangstart
pkilep:

nincshang:

         lea  ax,htbl
         mov  htblptr,ax

         pop  es
         ret
hang     endp


keslelts  proc
          ; * ;;;
          mov ax,ax            ;   kesleltetes
          mov ax,ax            ;   kesleltetes
          mov ax,ax            ;   kesleltetes
          mov ax,ax            ;   kesleltetes
          mov ax,ax            ;   kesleltetes
          mov ax,ax            ;   kesleltetes
          mov ax,ax            ;   kesleltetes
          mov ax,ax            ;   kesleltetes
          mov ax,ax            ;   kesleltetes
          ; * ;;;
          ret
keslelts  endp



; it kovetkeznek a szamkonvertalas rutinjai

main2   proc

        push ds
        push es
        assume ds:szamds,es:szamds,cs:cseg,ss:sseg
        mov  ax,szamds
        mov  ds,ax
        mov  es,ax

      ; cls

start2:
        mov      phon,0
        mov      phone,0
        mov      phont,0
        mov      stegesz,0
        mov      sttort,0

        call     seprt

            cmp      lsep,2
            jne      nemtort
            mov      ax,0
            mov      al,stegesz
            add      al,sttort
            cmp      al,20
            jbe      nemsokj
            movstr   valahanyad,phone
            jmp      prout

nemtort:
            mov      ax,0
            mov      al,stegesz
            cmp      al,20
            jae      soksok
            mov      bl,20
            sub      bl,al
            cmp      bl,sttort
            jae      nemsok
            mov      sttort,bl
nemsokj:    jmp      nemsok


soksok:
            cmp      sorsz,10
            je       soksokadik
            movstr   sok,phone
            jmp      prout
soksokadik:
            movstr   sokadik,phone
            jmp      prout
nemsok:


        sub30    stegesz
        sub30    sttort

        mov      ax,0
        mov      al,sorsz
        mul      lsep
        mov      sorsz,al

        jmp      cont
jexit:  jmp      exit2

cont:   movstr  stegesz,szamstr

        mov     al,sorsz
        mov     sorsz1,al
        cmp     lsep,2
        jnz     econv
        mov     sorsz,0

econv:  call    szamconv

        mov     al,sorsz1
        mov     sorsz,al

        movstr  phon,phone
        valax    stegesz,1,stegesz
        cmp      sorsz,10
        jz       t012
        cmp      ax,0
        jz       addnlj
        jmp      label1
addnlj: jmp      addnul

t012:   cmp      ax,0
        jnz      t1
        movstr   nulladik,phone
        jmp      prout
t1:     cmp      ax,1
        jnz      t2
        cmp      stegesz,1
        jnz      t2
        movstr   elso,phone
        jmp      prout
t2:     cmp      ax,2
        jnz      texit
        cmp      stegesz,1
        jnz      texit
        movstr   masodik,phone
texit:  jmp      prout

addnul: appnd    nulla,phone
        jmp      label1
notrt:  jmp      prout

label1: cmp     sttort,0
        jz      notrt
        cmp     lsep,2
        jz      tortc
        appnd   egesz,phone
tortc:  movstr  sttort,szamstr
        mov     phon,0
        call    szamconv
        movstr  phon,phont
        valax   sttort,1,sttort
        cmp     ax,0
        jnz     vant
        movstr  nulla,phont


vant:   cmp     sorsz,20
        jz      prout1
        mov     si,offset szne
        mov     ax,0
        mov     al,sttort
        dec     al
        mov     munka1,20
        mul     munka1
        add     si,ax
        appelem phont
        jmp     prout2

prout1: appnd   space1,phone
prout2: appnd   phont,phone
prout:  ; appnd   nextl,phone

        jmp exit2

         jz  startj
         jmp exit2
startj:  jmp start2
         dw 0e2bh

exit2:

         mov    ax,dseg
         mov    es,ax
         assume es:dseg
         mov    string1,0
         movstr phone,textlgt    ;     atmasoljuk a szamot a
         mov    ax,es:phnext     ;     az aktualis allapot elmentese
         mov    es:phnexts,ax
         mov    ax,dseg
         mov    ds,ax
         assume ds:dseg
         movstr phonlgt,phons
         pop es
         pop ds

         ret
main2    endp

;


szamconv  proc  near

        valax    szamstr,1,szamstr
        cmp      ax,0
        jnz      vaneg
        jmp      noconv
vaneg:
        mov      ax,0
        mov      al,szamstr
        mov      cl,3
scikl:  cmp      al,3
        jbe      sublk
        sub      al,cl
        jmp      scikl
sublk:  mov      subl,al
        mov      al,szamstr
        mov      maradek,al
        mov      cpos,1
        mov      plussz,0
        mov      told,0
        mov      csop,0

c1285:  cmp      sorsz,0
        jz       no1285
        mov      al,cpos
        add      al,2
        cmp      al,szamstr
        jb       no1285
        mov      al,szamstr
        inc      al
        sub      al,cpos
        mov      munka1,al
        valax    szamstr,cpos,munka1
        cmp      al,0
        jnz      no1285
        jmp      c1385
no1285:

c1290:  mov      si,offset szamstr
        mov      ax,0
        mov      al,cpos
        add      si,ax
        cmp      byte ptr [si],0
        jnz      no1290
        appnd    plussz,phon
        jmp      c1300
no1290: appnd    plussz,phon
        appnd    told,phon
c1300:  mov      si,offset szamstr
        mov      ax,0
        mov      al,cpos
        add      si,ax
        mov      al,[si]
        mov      index,al
        mov      si,offset szam
        mov      al,subl
        dec      al

        mov      munka1,30
        mul      munka1
        mov      munka1,20
        mul      munka1

        add      si,ax
        mov      ax,0
        mov      al,index
        mov      munka1,20
        mul      munka1
        add      si,ax
        push     si
        movelem  plussz
        pop      si
        appelem  csop

c1310:  mov      al,plussz
        cmp      al,0
        jbe      no1310
        mov      al,subl
        mov      lsubl,al
        mov      al,index
        mov      lindex,al
no1310:

c1320:  cmp      subl,2
        jnz      no1320
        mov      si,offset szam
        mov      al,4
        dec      al

        mov      munka1,30
        mul      munka1
        mov      munka1,20
        mul      munka1

        add      si,ax
        mov      ax,0
        mov      al,index
        mov      munka1,20
        mul      munka1
        add      si,ax
        movelem  told
        jmp      c1330
no1320: mov      told,0

c1330:  inc      cpos
        dec      subl
        cmp      maradek,0
        jnz      c1340
        mov      maradek,1

c1340:  cmp      subl,0
        jnz      no1340
        cmp      csop,0
        jz       no1340
        cmp      sorsz,0
        jz       nextc
        mov      al,szamstr
        inc      al
        sub      al,cpos
        mov      munka1,al
        valax    szamstr,cpos,munka1
        cmp      al,0
        jbe      no1340
nextc:  mov      si,offset sznev
        mov      ax,0
        mov      al,maradek
        dec      ax
        mov      munka1,20
        mul      munka1
        add      si,ax
        appelem  plussz
no1340:

c1345:  cmp      subl,0
        jnz      no1345
        cmp      csop,0
        jz       no1345
        cmp      sorsz,0
        jz       no1345
        mov      al,szamstr
        inc      al
        sub      al,cpos
        mov      munka1,al
        valax    szamstr,cpos,munka1
        cmp      al,0
        jnz      no1345
        mov      si,offset sznev

        mov      ax,0
        mov      al,sorsz
        shl      ax,1
        add      al,maradek

        dec      ax
        mov      munka1,20
        mul      munka1
        add      si,ax
        appelem  phon
no1345:

c1347:  cmp      subl,0
        jnz      no1347
        cmp      csop,0
        jz       no1347

        cmp      sorsz,0
        jz       no1347

        mov      al,szamstr
        inc      al
        sub      al,cpos
        mov      munka1,al
        valax    szamstr,cpos,munka1
        cmp      al,0
        jnz      no1347
        mov      al,cpos
        cmp      al,szamstr
        jae      no1347
        jmp      c1490
jc1285: jmp      c1285

no1347:

c1350:  cmp      subl,0
        jnz      c1360
        mov      subl,3
        mov      csop,0

c1360:  dec      maradek

c1370:  mov      al,cpos
        cmp      al,szamstr
        jbe      jc1285

c1375:  cmp      sorsz,0
        ja       c1385

c1380:  mov      si,offset szamstr
        mov      ax,0
        mov      al,cpos
        add      si,ax
        dec      si
        cmp      byte ptr [si],0
        jz       y1380
        appnd    plussz,phon
        appnd    told,phon
        jmp      c1382
y1380:  appnd    plussz,phon

c1382:  jmp      c1390

c1385:
        mov      si,offset szam
        mov      al,lsubl
        dec      al

        mov      munka1,30
        mul      munka1
        mov      munka1,20
        mul      munka1

        add      si,ax
        mov      ax,0
        mov      al,lindex
        add      al,sorsz
        mov      munka1,20
        mul      munka1
        add      si,ax
        appelem  phon
c1390:
noconv:
            ret

c1490:
        ;appnd    plussz,phon
        ;
         appnd    phon,plussz
         mov phon,0                           ;    probalkozas
         appnd    plussz,phon
        ;
        jmp      c1390

szamconv    endp





seprt   proc       ; a string1 -ben levo szamot egesz es tort reszre bontjuk

        mov    stegesz,0
        mov    sttort,0
        mov    sorsz,0
        mov    lsep,0

        mov    cx,0
        mov    cl,string1
        jcxz   exseprt
        lea    si,string1
        inc    si
        lea    di,stegesz
        inc    di
        mov    munka1,0
nextch: mov       al,[si]
        cmp       al,'.'
        je        finde
        cmp       al,'/'
        je        finda
        inc       munka1
        mov       [di],al
        inc       di
        inc       si
        loop      nextch
        mov       al,munka1
        mov       stegesz,al
        mov       sttort,0
        jmp       exseprt
finde:  mov       lsep,1
        jmp       find
finda:  mov       lsep,2
        mov       sorsz,10
        jmp       find
find:   mov       al,munka1
        mov       stegesz,al
        mov       munka1,0
        inc       si
        lea       di,sttort
        inc       di
        dec       cx
        jcxz      nm1
tpakol: mov       al,[si]
        mov       [di],al
        inc       munka1
        inc       si
        inc       di
        loop      tpakol
        mov       al,munka1
        mov       sttort,al
        jmp       exseprt
nm1:    mov       sorsz,10            ; tizedes pont van de nincs tort resz
                                      ; vagyis  sorszam
exseprt:
        ret
seprt   endp




; a szamkonvertalas rutinjainak vege







cseg     ends
         end       main

