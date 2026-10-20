async function readJson(file) {
    const response = await fetch(file, {cache: 'no-store'});
    if (!response.ok) throw new Error(`${file}: HTTP ${response.status}`);
    return response.json();
}

function documentLink(url, label) {
    const link = document.createElement('a');
    const parsed = new URL(url, window.location.href);
    if (!['https:', 'http:'].includes(parsed.protocol)) throw new Error('Ungültiger Dokumentlink');
    link.href = parsed.href;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = label;
    return link;
}

async function loadHistory(file, containerId, stampId) {
    const container = document.getElementById(containerId);
    try {
        const history = await readJson(file);
        container.replaceChildren();
        if (stampId) {
            document.getElementById(stampId).textContent = history.length
                ? `Letzter Scan: ${history[0].datum}` : 'Noch kein Scan durchgeführt.';
        }
        if (!history.length) {
            container.textContent = 'Noch keine Änderungen aufgezeichnet.';
            return;
        }
        for (const entry of history) {
            const paragraph = document.createElement('p');
            const date = document.createElement('strong');
            date.textContent = `${entry.datum}: `;
            paragraph.append(date);
            if (!entry.funde.length) paragraph.append('✅ Scan durchgeführt, keine Änderungen.');
            for (const change of entry.funde) {
                const tag = document.createElement('span');
                tag.className = change.typ === 'NEU' ? 'neu-tag' : 'update-tag';
                tag.textContent = `[${change.typ}] `;
                paragraph.append(document.createElement('br'), tag,
                    document.createTextNode(`${change.bezeichnung} (`), documentLink(change.url, 'Link'), ')');
            }
            container.append(paragraph);
        }
    } catch (error) {
        container.textContent = 'Fehler beim Laden der Historie oder noch nicht verfügbar.';
        console.error(error);
    }
}

async function loadDocuments(file, bodyId, tableId, loadingId, metadata = false) {
    const loading = document.getElementById(loadingId);
    try {
        const data = await readJson(file);
        const body = document.getElementById(bodyId);
        body.replaceChildren();
        if (!Object.keys(data).length) {
            loading.textContent = 'Noch kein erfolgreicher Scan verfügbar.';
            return;
        }
        for (const info of Object.values(data)) {
            const row = document.createElement('tr');
            const fields = metadata ? ['Titel', 'Dokumenttyp', 'Sprache', 'Groesse'] : ['Titel'];
            for (const field of fields) {
                const cell = document.createElement('td');
                cell.textContent = info[field] || '–';
                row.append(cell);
            }
            const linkCell = document.createElement('td');
            const label = metadata ? 'Download' : info.Link.length > 80 ? info.Link.slice(0, 77) + '...' : info.Link;
            linkCell.append(documentLink(info.Link, label));
            if (info.Geschuetzt) linkCell.append(' (Nutzungsbedingungen bei Fronius bestätigen)');
            row.append(linkCell);
            body.append(row);
        }
        loading.style.display = 'none';
        document.getElementById(tableId).style.display = 'table';
    } catch (error) {
        loading.textContent = 'Fehler beim Laden der Dokumente.';
        console.error(error);
    }
}

async function loadFroniusStatus() {
    const container = document.getElementById('fronius-status');
    try {
        const status = await readJson('fronius_status.json');
        if (status.ok) {
            container.textContent = `Letzter erfolgreicher Scan: ${status.letzter_erfolg} (Europe/Zurich) · ${status.anzahl} Dokumente`;
        } else {
            container.style.color = '#a93226';
            container.textContent = `Scan fehlgeschlagen (${status.versuch}). ` +
                (status.letzter_erfolg ? `Angezeigt wird der Stand vom ${status.letzter_erfolg}.` : 'Noch kein erfolgreicher Scan verfügbar.');
        }
    } catch (error) {
        container.textContent = 'Scanstatus nicht verfügbar.';
        console.error(error);
    }
}

loadHistory('history.json', 'history-inhalt', 'zeitstempel');
loadDocuments('sma_daten.json', 'inhalt', 'tabelle', 'loading');
loadHistory('fronius_history.json', 'fronius-history');
loadDocuments('fronius_daten.json', 'fronius-documents', 'fronius-table', 'fronius-loading', true);
loadFroniusStatus();
