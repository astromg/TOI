# TOI
Telescope Operator Interface

### odpalanie: 
$ ./toi.py

- _toi.py_ - Monitor do sygnalow i komunikacji z AutoSlew, odpala tez wszytskie okna GUI
- _tel_gui.py_ - nic ciekawego, ale tylko tutaj jest **EXIT**
- _mnt_gui.py_ - Mount Controll - uzywa Monitora
- _pery_gui.py_ - sterowanie peryferiami - swiatla, M3, etc. 
- _instrument_gui.py_ - instrument Window
- _plan_gui.py_ - Plan Manager
- _sky_gui.py_ - Radarek nieba


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

## MOUNT + PERYPHERICAL (mnt_gui.py pery_gui.py)
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
