# SMA und Fronius Dokumentmonitor

Die Webseite `index.html` zeigt die vorhandenen SMA-Produkte und **Fronius Symo
GEN24 3.0 Plus SC** mit getrennten Beständen und Änderungshistorien an.

## Fronius

`fronius_scraper.py` verwendet den Suchendpunkt der Fronius-Webseite
(`/api/data/search/getdownloadcenter`) für die Artikelnummer **4,210,190,002**.
Die erforderliche Seiten-ID wird bei jedem Scan aus dem aktuellen Download-Center
ermittelt. Alle Dokumenttypen und Sprachen werden ohne Länderfilter abgerufen.
Der Scanner liest sämtliche Ergebnisseiten und prüft die Gesamtzahl sowie doppelte
Links. Ein Fehler oder eine unvollständige Antwort führt zu einem fehlgeschlagenen
Scan; der letzte vollständige Bestand und dessen Historie bleiben erhalten.

Gespeichert werden `fronius_daten.json`, `fronius_history.json` (letzte 30 Scans)
und `fronius_status.json` (Scanstatus mit Zeit in Europe/Zurich). Der erste Scan
führt alle Dokumente als NEU auf. Weitere Scans erkennen neue Download-Links und
Änderungen an Titel, Sprache, Dokumenttyp, Dateigröße oder Schutzkennzeichnung.
Wie beim SMA-Monitor werden entfernte Dokumente nicht als Änderung gemeldet;
sie verschwinden beim nächsten vollständigen Scan aus dem aktuellen Bestand.
Dateiinhalte werden nicht heruntergeladen oder gehasht. Änderungen bei gleichem
Link und unveränderten Metadaten sind daher nicht erkennbar.

Der Workflow **SMA and Fronius Monitor Daily Scan** läuft täglich um **08:00 UTC**
(09:00 Schweizer Winterzeit / 10:00 Sommerzeit) und ist manuell über GitHub Actions
startbar. Er speichert Ergebnisse beider Hersteller unabhängig voneinander und
markiert den Lauf bei einem Scanfehler als fehlgeschlagen. Die tägliche Ausführung
beginnt nach Übernahme in den Standardbranch. Die Webseite zeigt Fronius-Fehler
und den Zeitpunkt des letzten erfolgreichen Scans an.

## Lokal ausführen

```sh
pip install -r requirements.txt
python fronius_scraper.py
python -m unittest discover -s tests -v
python -m http.server 8000
```

Für einen Probelauf ohne Änderung der gespeicherten Daten:

```sh
python fronius_scraper.py --data-dir work/fronius-check
```

Fronius benötigt keinen Browser; SMA verwendet weiterhin Playwright
(`playwright install chromium`). Systemweite Proxy- und Zertifikatseinstellungen
werden für die Fronius-Anfragen übernommen. Der Suchendpunkt ist eine interne
Schnittstelle der Webseite; Strukturänderungen werden als Scanfehler gemeldet.
