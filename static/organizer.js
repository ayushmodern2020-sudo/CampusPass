let scanner = null;
let running = false;
let busy = false;

const resultBox = document.getElementById('result');
const cameraStatus = document.getElementById('camera-status');
const tokenInput = document.getElementById('token');
const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';

function setResult(type, title, message, detail = '') {
    resultBox.className = `result ${type}`;
    resultBox.replaceChildren();
    const titleNode = document.createElement('span');
    titleNode.textContent = title;
    const messageNode = document.createElement('span');
    messageNode.textContent = message;
    resultBox.append(titleNode, messageNode);
    if (detail) {
        const detailNode = document.createElement('small');
        detailNode.textContent = detail;
        resultBox.append(detailNode);
    }
}

async function verifyToken(token) {
    if (busy) return;
    if (!token) {
        setResult('invalid', 'INVALID TICKET', 'No token was provided.');
        return;
    }

    busy = true;
    setResult('idle', 'VERIFYING', 'Checking signature and ticket status.');

    try {
        const response = await fetch('/api/checkin', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': csrfToken
            },
            credentials: 'same-origin',
            body: JSON.stringify({token})
        });

        const data = await response.json();

        if (response.status === 401) {
            setResult('invalid', 'SESSION EXPIRED', 'Please sign in to the organizer portal again.');
            return;
        }

        if (data.status === 'CHECKED-IN') {
            setResult('checked', '✓ CHECKED-IN', `${data.participant} · ${data.event}`, `${data.checked_in_at} · verified by ${data.checked_in_by || 'organizer'}`);
        } else if (data.status === 'ALREADY USED') {
            setResult('used', '⚠ ALREADY USED', `${data.participant} · ${data.event}`, `${data.checked_in_at || 'Previous check-in'} · verified by ${data.checked_in_by || 'organizer'}`);
        } else {
            setResult('invalid', `✕ ${data.status || 'INVALID TICKET'}`, data.message || 'Ticket validation failed.');
        }
    } catch (error) {
        setResult('invalid', 'NETWORK ERROR', 'The verification request could not be completed.');
    } finally {
        busy = false;
    }
}

const verifyButton = document.getElementById('verify-token');
if (verifyButton) {
    verifyButton.addEventListener('click', () => verifyToken(tokenInput.value.trim()));
}

if (tokenInput) {
    tokenInput.addEventListener('keydown', event => {
        if (event.ctrlKey && event.key === 'Enter') {
            verifyToken(tokenInput.value.trim());
        }
    });
}

const startButton = document.getElementById('start-scan');
if (startButton) {
    startButton.addEventListener('click', async () => {
        if (running) return;

        scanner = new Html5Qrcode('reader');

        try {
            await scanner.start(
                {facingMode: 'environment'},
                {fps: 10, qrbox: {width: 250, height: 250}},
                async decodedText => {
                    tokenInput.value = decodedText;
                    await verifyToken(decodedText);
                    await stopScanner();
                },
                () => {}
            );

            running = true;
            cameraStatus.textContent = 'Camera is scanning. Point it at the attendee QR code.';
        } catch (error) {
            running = false;
            cameraStatus.textContent = 'Camera could not start. Check browser camera permission and try again.';
        }
    });
}

async function stopScanner() {
    if (!scanner) return;

    try {
        if (running) {
            await scanner.stop();
        }
        await scanner.clear();
    } catch (error) {}

    running = false;
    cameraStatus.textContent = 'Camera is idle.';
}

const stopButton = document.getElementById('stop-scan');
if (stopButton) {
    stopButton.addEventListener('click', stopScanner);
}

document.querySelectorAll('.stats-button').forEach(button => {
    button.addEventListener('click', async () => {
        const eventId = button.dataset.eventId;
        const target = document.getElementById(`event-status-${eventId}`);
        target.textContent = 'Refreshing...';

        try {
            const response = await fetch(`/api/event/${eventId}`, {
                credentials: 'same-origin'
            });
            const data = await response.json();

            if (!response.ok) {
                target.textContent = data.error || 'Unable to load stats.';
                return;
            }

            target.textContent = `${data.registered} registered · ${data.checked_in} checked in · ${data.remaining} remaining`;
        } catch (error) {
            target.textContent = 'Unable to load live statistics.';
        }
    });
});
