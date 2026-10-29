# TOI
Telescope Operator Interface

### odpalanie:
If installed by `poetry` (see below)
```
$ toi
```   
otherwise
```
$ ./toi.py
```

- _toi.py_ - Monitor do sygnalow i komunikacji z AutoSlew, odpala tez wszytskie okna GUI
- _obs_gui.py_ - okno obserwacji = okno glowne: lampki serwisow, warunki, tabela teleskopow, log, menu ⚙
- _mnt_gui.py_ - Mount Controll - uzywa Monitora
- _instrument_gui.py_ - instrument Window
- _plan_gui.py_ - Plan Manager
- _sky_gui.py_ - Radarek nieba (tu jest **EXIT**)
- _fits_gui.py_ - podglad FITS
- _aux_gui.py_ - okno Aux z zakladkami: Telescope, Tasks, Optical path, Calibration, Focus, Guider, Plan Runner, Conditions

## UKLAD OKIEN (od 27.10.2026)
- Okno obserwacji jest oknem glownym, a Mount, Instrument, Sky, Plan, FITS i Aux to panele w nim (dock). Panel
  mozna przeciagnac za pasek tytulu w inne miejsce, polozyc na innym jako zakladke albo wypiac na drugi monitor.
- Pasek tytulu panelu ma kolor i nazwe aktywnego teleskopu (np. "Mount · jk15").
- Uklad zapisuje sie przy zamknieciu TOI (krzyzyk na oknie obserwacji + Yes albo EXIT) osobno dla kazdego
  ustawienia ekranow (laptop, laptop + monitor, stanowisko) i wraca przy starcie. Ctrl+C w terminalu go nie zapisuje.
- Menu ⚙ (prawy dolny rog okna obserwacji): wyciaga dowolny panel / zakladke Aux na wierzch, **Reset layout**
  wraca do ukladu domyslnego (dawne rozmiary okien; na malym ekranie panele ida jako zakladki przy Sky).
- Zakladki Aux przelaczaja sie same: zmiana portu M3 -> Optical path, start OB SKYFLAT/DOMEFLAT -> Calibration,
  start OB FOCUS -> Focus.
- Lampki u gory okna obserwacji: TIC, NATS, DOME FLW (heartbeat dome followera), FITS DWL i OFP (RPC alive
  oca-fits-proc), FLAT OW i WEATHER OW (RPC alive overwatchy `rpc.overwatch.oca.<nazwa>.alive`).

## OBSERWATORZY NOCY
- Lista osob w `observers.yaml` (katalog glowny repo) - tu dopisujemy stalych obserwatorow (samo nazwisko albo
  wpis `{name: ...}` na pozniejsze dane).
- W oknie tabela z wyszukiwarka; na starcie zaznaczeni sa obserwatorzy z ostatniego wpisu (poprzedniej nocy),
  zaznaczeni sa na gorze tabeli.
- Wpis wazny do codziennego resetu o `toi.observers_reset_ut` (godzina UT, domyslnie 15 = poludnie latem w Chile);
  potem okno "Observers tonight" wyskakuje samo; mozna zaznaczyc osoby z listy
  i wpisac gosci w polu Other. "Later" odklada pytanie o 30 min.
- Wybor idzie na NATS (`tic.status.ocm.observers`), wiec widza go wszystkie stanowiska; okno znika wszedzie, gdy
  ktos zapisze. Obserwatorzy sa na przycisku miedzy PING a ⚙ - klikniecie otwiera okno do poprawki.
- "Only this TOI": wybor tylko dla tej sesji, nic nie idzie na NATS (np. testy z Warszawy) - przycisk pokazuje
  wtedy "Observers (this TOI only)", a pozostale stanowiska maja dalej swoj wpis.

## KONFIGURACJA (toi_config.yaml) - wpisy dodane 26-27.10.2026
- per teleskop: `focus_step` (domyslny krok autofocusa, zamiast `default_step` z TIC), `focus_method`,
  `focus_methods` (nazwy z `pyaraucaria.focus`),
- `toi.oca_manual_url` - manual w intranecie dla zakladki Telescope (`http://docker.oca.lan:8081`): po lewej strona
  `telescope_<tel>`, po prawej changelog `telescope_<tel>_changelog`,
- `toi.observers_reset_ut` - godzina UT codziennego resetu obserwatorow nocy (domyslnie 15),
- `toi.alive_subjects` - subjecty RPC alive overwatchy (puste = lampka szara).
- `toi.conditions_subjects` - `seeing` i `zero_point` obserwatorium z weather_overwatch, pola "Seeing" i "Zero point"
  w oknie obserwacji (brak = "--").
- Konfiguracji TIC (ocabox-config-ocm) TOI tylko czyta; domyslny gain / read mode bierze z `flags: ['default']`.


## MASTER WINDOW (tel_gui.py)
- polaczyc ze SkyView?
- dodac zakladki z teleskopami
- dodac odpalanie Mount/instrument plan controler
- wyswietlanie innych teleskopow?


## PLAN WINDOW (plan_gui) 
- Zintegrowac z TIC - synchornizacja planow, next object i logow obserwacyjnych
- przemyslec jak kontrolowac alerty - oddzielne okno z zaznaczaniem  - focu calibration 2000s, etc. ??
- pamietac o ob_id i plan_id
- co wyslwietlac w tabelce - ikonki, nazwa, uwagi, H, Az, seq, tot_exp, obs_id
- dodac sprawdzanie parametrow obserwacji
- doadc przycicsk i wiedget _plot night plan_
- w tabelce wyswietlac LOG z obserwacji z mozliwoscia edytowania
- _LoadPlan_ -> wczytywac zgodnie z formatem plikow - synchronizacja z TIC
- _stop_ i _start_ -> TIC odpala automat obserwacyjny 
- _next_ _skip_ i _stop_ zmienic ikonki i przemyslec
- _del all_ - nieaktywne
- _del_ _up_ _down_ _first_ _last_ _swap_ - READY, ale zamienic first i last z up i down
- _add_ - dodac caly widget z mozliwoscia dodania katalogu, obiektu, markerow...
- _edit_ - widget do edytowania paramatrow programu (exp time, etc.)

## SKY VIEW (sky_gui)
- dwa mody - wybieranie z planu obiektow / free mode
- interakcja SKY <-->  plan controler / tel controler
- wyswietlanie ut, sid, jd, programu, tel status, dome status, mirror covers, lights, flatfiled lights
- dodac ksiezyc, slonce, (planety?)

## MOUNT + PERYPHERICAL (mnt_gui.py)
- uzywa **Monitor** 
- polaczyc dwa okna
- dodac _fans_ on off / power
- dodac DomeFlat light / power
- dodac Park Dome

## INSTRUMENT CONTROLL 
- zrobic nadwidget z tabami do roznych instrumentow? 
- ostrzezewnie jak nie jest M3 skierowane na instrument
- Mode - zdefiniowac plik? 
- Subraster - pliki z definicjami wspolrzednych

## OKNO GUIDERA 
- nie ma - nie ma, nie wiem jak dzialac i synchronizowac

## FOCUS ADJUST (automatyczna korekta focusa)
Wlaczany przelacznikiem **FOCUS ADJUST** w oknie montazu. Stan przelacznika jest wspolny dla wszystkich
instancji TOI (`tic.status.<tel>.toi.switch_synchro`).

**Jak dziala:** adjust poprawia focus tylko o zmiane temperatury i wilgotnosci (stacja Davis) **od momentu
ostatniego ustawienia focusa**. Za kazdym razem, gdy TOI ustawia focus, zapamietuje pozycje i warunki
jako wartosc referencyjna:
- reczne **SET** w oknie montazu (`manual`),
- wynik autofocusa, rowniez z planu - OB `FOCUS` (`autofocus`),
- powrot do poprzedniej pozycji po nieudanym autofocusie (`autofocus_failed`),
- korekta zrobiona przez sam adjust (`focus_adjust`).

Docelowy focus:
```
target = ref_position + model(T_teraz, H_teraz) - model(T_ref, H_ref)
model  = a0 + aTemp*T + aHum*H          (wspolczynniki per teleskop, toi.py: focus_model)
```
Recznie ustawiony focus (takze celowy defocus) jest wiec zachowany jako offset, a adjust tylko prowadzi go
za temperatura.

**Kiedy rusza focuserem:** co ~1 s, tylko TOI majace dostep do teleskopu, gdy przelacznik jest ON, nie trwa
autofocus, kamera nie eksponuje/czyta (stan kamery 1-4) i `|target - ref_position| > 5` krokow. Kazda korekta
staje sie nowa referencja, wiec poprawki sie nie kumuluja.

**Gdzie to widac:**
- tooltip na polu pozycji focusa w oknie montazu - referencja (pozycja, zrodlo, czas, T/H) i aktualny target,
- pole pozycji jest zolte, gdy focuser rozni sie od targetu o wiecej niz 10 krokow,
- log TOI przy kazdej korekcie: `adjusting focus 15320 -> 15293 (ref: manual ..., 8.4C/62% -> 7.1C/65%)`.

**NATS:**
- `tic.status.<tel>.toi.focus_reference` - aktualna referencja
  `{position, davis_temperature, davis_humidity, time, source}`,
- `tic.status.<tel>.toi.focus_record` - tylko wyniki autofocusa (log w oknie focusa).

**Ograniczenia:**
- referencje zapisuje tylko TOI. Jesli focus przestawi inna aplikacja, adjust przywroci `ref + delta`. Inne
  aplikacje ruszajace focuserem powinny publikowac na `focus_reference`,
- brak telemetrii Davis w chwili ustawiania focusa: referencja bez T/H, adjust nieaktywny do nastepnego
  ustawienia focusa (ostrzezenie w logu),
- po pierwszym wdrozeniu `focus_reference` jest pusty, wiec adjust zacznie dzialac po pierwszym SET albo
  autofocusie.

## Installation
#### Install using the [`poetry` tool](https://python-poetry.org/docs/basic-usage/)
This procedure installs all dependences includin proper python version in isolated virtual environment.
Python 3.11-3.14 (3.14 also needs tpg allowing it, which it does since 27.10.2026).
Also, the command line command `toi` will be created for easy running the executable in proper environment.
1. [Install poetry](https://python-poetry.org/docs/#installation)
2. Clone the project
```
    git clone https://github.com/astromg/TOI.git
    cd TOI
```
3. Install project and dependences
```
    poetry install
```
4. Run
```
    toi
```


