/**
 * Observer Client - Classifier Training Button
 * Triggers train_classifier.py via API and shows live output in a modal.
 */

var _clsPolling = null;
var _clsModal = null;

function trainClassifier(backfill) {
    var endpoint = backfill
        ? '/admin/classifier/train-and-backfill'
        : '/admin/classifier/train';

    var btn = backfill
        ? document.getElementById('trainBackfillBtn')
        : document.getElementById('trainClassifierBtn');
    var hint = document.getElementById('classifierHint');

    // Disable both buttons
    document.getElementById('trainClassifierBtn').disabled = true;
    document.getElementById('trainBackfillBtn').disabled = true;
    if (btn) btn.textContent = 'Starting...';

    fetch(endpoint, {
        method: 'POST',
        headers: { 'X-API-Key': (typeof API_KEY !== 'undefined' ? API_KEY : '') }
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (!data.success) {
            if (hint) hint.textContent = data.message || 'Failed to start';
            _clsResetButtons();
            return;
        }

        if (btn) btn.textContent = 'Running...';
        if (hint) hint.textContent = 'Training in progress...';

        // Open output modal
        _clsShowModal(backfill ? 'Train + Backfill' : 'Train Classifier');

        // Start polling
        _clsStartPolling();
    })
    .catch(function(err) {
        if (hint) hint.textContent = 'Error: ' + err.message;
        _clsResetButtons();
    });
}

function _clsResetButtons() {
    var btn1 = document.getElementById('trainClassifierBtn');
    var btn2 = document.getElementById('trainBackfillBtn');
    if (btn1) { btn1.disabled = false; btn1.textContent = 'Train Classifier'; }
    if (btn2) { btn2.disabled = false; btn2.textContent = 'Train + Backfill'; }
}

function _clsShowModal(title) {
    // Remove existing
    if (_clsModal) _clsModal.remove();

    var overlay = document.createElement('div');
    overlay.id = 'clsModalOverlay';
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.6);z-index:10000;display:flex;align-items:center;justify-content:center;';

    var box = document.createElement('div');
    box.style.cssText = 'background:var(--bg-secondary);border:1px solid var(--border);border-radius:6px;width:700px;max-width:90vw;max-height:80vh;display:flex;flex-direction:column;';

    // Header
    var header = document.createElement('div');
    header.style.cssText = 'display:flex;justify-content:space-between;align-items:center;padding:12px 16px;border-bottom:1px solid var(--border);flex-shrink:0;';
    header.innerHTML = '<span style="font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:1px;color:var(--accent-primary);">' + title + '</span>'
        + '<span id="clsModalStatus" style="font-size:10px;color:var(--text-muted);">Running...</span>';

    // Close button
    var closeBtn = document.createElement('button');
    closeBtn.textContent = '\u00D7';
    closeBtn.style.cssText = 'background:none;border:none;color:var(--text-secondary);font-size:20px;cursor:pointer;padding:0 4px;';
    closeBtn.onclick = function() { _clsCloseModal(); };
    header.appendChild(closeBtn);

    // Output area
    var output = document.createElement('pre');
    output.id = 'clsModalOutput';
    output.style.cssText = 'flex:1;overflow-y:auto;padding:12px 16px;margin:0;font-size:11px;font-family:monospace;color:var(--text-primary);line-height:1.5;white-space:pre-wrap;word-break:break-word;min-height:200px;';
    output.textContent = 'Waiting for output...\n';

    box.appendChild(header);
    box.appendChild(output);
    overlay.appendChild(box);

    // Click outside to close (only after done)
    overlay.addEventListener('click', function(e) {
        if (e.target === overlay && !_clsPolling) _clsCloseModal();
    });

    document.body.appendChild(overlay);
    _clsModal = overlay;
}

function _clsCloseModal() {
    if (_clsModal) {
        _clsModal.remove();
        _clsModal = null;
    }
    if (_clsPolling) {
        clearInterval(_clsPolling);
        _clsPolling = null;
    }
}

function _clsStartPolling() {
    var lastLineCount = 0;

    _clsPolling = setInterval(function() {
        fetch('/admin/classifier/status', {
            headers: { 'X-API-Key': (typeof API_KEY !== 'undefined' ? API_KEY : '') }
        })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            var outputEl = document.getElementById('clsModalOutput');
            var statusEl = document.getElementById('clsModalStatus');

            if (outputEl && data.output && data.output.length > 0) {
                outputEl.textContent = data.output.join('\n') + '\n';
                // Auto-scroll to bottom if near bottom
                if (outputEl.scrollHeight - outputEl.scrollTop - outputEl.clientHeight < 100) {
                    outputEl.scrollTop = outputEl.scrollHeight;
                }
            }

            if (!data.running) {
                clearInterval(_clsPolling);
                _clsPolling = null;

                var hint = document.getElementById('classifierHint');
                if (data.exit_code === 0) {
                    if (statusEl) statusEl.textContent = 'Complete';
                    if (statusEl) statusEl.style.color = 'var(--accent-green)';
                    if (hint) hint.textContent = 'Training complete';
                } else {
                    if (statusEl) statusEl.textContent = 'Failed (exit ' + data.exit_code + ')';
                    if (statusEl) statusEl.style.color = 'var(--accent-red, #ef4444)';
                    if (hint) hint.textContent = 'Training failed — check output';
                }
                _clsResetButtons();
            }

            lastLineCount = data.line_count || 0;
        })
        .catch(function() {
            // Ignore transient fetch errors during poll
        });
    }, 1500);
}
