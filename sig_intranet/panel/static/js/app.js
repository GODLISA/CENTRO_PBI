/* ============================================
   app.js - Panel SIG con polling de estado
   ============================================ */

document.addEventListener('DOMContentLoaded', function () {
    console.log('[SIG] app.js cargado');

    // --- Confirmación antes de cerrar sesión ---
    var logoutLinks = document.querySelectorAll('.logout-btn');
    logoutLinks.forEach(function (link) {
        link.addEventListener('click', function (e) {
            if (!confirm('¿Deseas cerrar sesión?')) {
                e.preventDefault();
            }
        });
    });

    // =============================================
    // Configuración — Actualizar Paneles (solo staff)
    // =============================================
    var POLL_INTERVAL = 2000; // Consultar cada 2 segundos
    var pollTimer = null;

    var btnActualizar = document.getElementById('btn-actualizar');
    if (!btnActualizar) {
        console.log('[SIG] Botón #btn-actualizar no encontrado (usuario no es staff). Polling desactivado.');
        return;
    }

    var scriptTag = document.querySelector('script[data-actualizar-url]');
    if (!scriptTag) {
        console.error('[SIG] No se encontró <script> con data-actualizar-url. Verifica panel.html.');
        return;
    }

    var actualizarUrl  = scriptTag.getAttribute('data-actualizar-url');
    var estadoUrlBase  = scriptTag.getAttribute('data-estado-url-base');
    var csrfToken      = scriptTag.getAttribute('data-csrf-token');

    console.log('[SIG] Config:', { actualizarUrl: actualizarUrl, estadoUrlBase: estadoUrlBase, csrfToken: csrfToken ? 'OK' : 'VACÍO' });

    // Elementos del panel de estado
    var statusPanel   = document.getElementById('job-status-panel');
    var statusIcon    = document.getElementById('job-status-icon');
    var statusLabel   = document.getElementById('job-status-label');
    var statusDetail  = document.getElementById('job-status-detail');
    var statusClose   = document.getElementById('job-status-close');
    var progressFill  = document.getElementById('job-progress-fill');

    // =============================================
    // Botón: Ejecutar actualización
    // =============================================
    console.log('[SIG] Botón #btn-actualizar encontrado. Registrando click handler.');

    btnActualizar.addEventListener('click', function () {
        console.log('[SIG] Click en Actualizar Paneles');
        if (btnActualizar.disabled) {
            console.log('[SIG] Botón deshabilitado, ignorando click.');
            return;
        }

        // Bloquear botón
        lockButton();
        updateStatus('SENDING', '🟡', 'Enviando solicitud...', '');
        showStatusPanel();

        console.log('[SIG] Enviando POST a:', actualizarUrl);
        fetch(actualizarUrl, {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrfToken,
                'Content-Type': 'application/json'
            },
            credentials: 'same-origin'
        })
        .then(function (res) {
            console.log('[SIG] Respuesta recibida:', res.status, res.statusText);
            if (!res.ok) {
                return res.text().then(function (txt) {
                    throw new Error('HTTP ' + res.status + ': ' + txt.substring(0, 200));
                });
            }
            return res.json();
        })
        .then(function (data) {
            console.log('[SIG] Datos:', JSON.stringify(data));
            if (data.success && data.data && data.data.jobId) {
                // Recibimos jobId → iniciar polling
                var jobId = data.data.jobId;
                updateStatus('PENDING', '🟡', 'En cola...', 'Job: ' + jobId);
                startPolling(jobId);
            } else if (data.success) {
                // Éxito sin jobId (ejecución inmediata)
                updateStatus('COMPLETED', '🟢', '¡Completado!', data.message || 'Ejecución exitosa');
                setProgress(100);
                unlockButton();
            } else {
                updateStatus('FAILED', '🔴', 'Error', data.message || 'Error desconocido');
                unlockButton();
            }
        })
        .catch(function (err) {
            console.error('[SIG] Error en fetch:', err);
            updateStatus('FAILED', '🔴', 'Error de conexión', err.message);
            unlockButton();
        });
    });

    // =============================================
    // Polling: consultar estado cada 2s
    // =============================================
    function startPolling(jobId) {
        stopPolling();
        setProgress(10);
        console.log('[SIG] Iniciando polling para jobId:', jobId);

        pollTimer = setInterval(function () {
            var url = estadoUrlBase + jobId + '/';
            fetch(url, {
                method: 'GET',
                credentials: 'same-origin'
            })
            .then(function (res) {
                if (!res.ok) {
                    return res.text().then(function (txt) {
                        throw new Error('HTTP ' + res.status + ': ' + txt.substring(0, 200));
                    });
                }
                return res.json();
            })
            .then(function (data) {
                if (!data.success) {
                    updateStatus('FAILED', '🔴', 'Error al consultar', data.message || '');
                    stopPolling();
                    unlockButton();
                    return;
                }

                var job = data.data || data;
                var estado = (job.status || job.estado || '').toUpperCase();

                switch (estado) {
                    case 'PENDING':
                    case 'QUEUED':
                        updateStatus('PENDING', '🟡', 'En cola...', 'Esperando turno de ejecución');
                        setProgress(20);
                        break;

                    case 'RUNNING':
                    case 'PROCESSING':
                        updateStatus('RUNNING', '🔵', 'Ejecutando...', job.message || 'Script en ejecución');
                        setProgress(60);
                        break;

                    case 'COMPLETED':
                    case 'SUCCESS':
                    case 'DONE':
                        updateStatus('COMPLETED', '🟢', '¡Completado!', job.message || job.result || 'Actualización exitosa');
                        setProgress(100);
                        stopPolling();
                        unlockButton();
                        showToast('✅ Actualización completada', 'success');
                        break;

                    case 'FAILED':
                    case 'ERROR':
                        updateStatus('FAILED', '🔴', 'Falló', job.message || job.error || 'Error durante la ejecución');
                        setProgress(100);
                        stopPolling();
                        unlockButton();
                        showToast('❌ La actualización falló', 'error');
                        break;

                    default:
                        updateStatus('PENDING', '🟡', 'Estado: ' + estado, JSON.stringify(job));
                        break;
                }
            })
            .catch(function (err) {
                updateStatus('FAILED', '🔴', 'Error de conexión', err.message);
                stopPolling();
                unlockButton();
            });
        }, POLL_INTERVAL);
    }

    function stopPolling() {
        if (pollTimer) {
            clearInterval(pollTimer);
            pollTimer = null;
        }
    }

    // =============================================
    // UI: Panel de estado
    // =============================================
    function showStatusPanel() {
        if (statusPanel) statusPanel.classList.remove('hidden');
    }

    function hideStatusPanel() {
        if (statusPanel) statusPanel.classList.add('hidden');
    }

    function updateStatus(state, icon, label, detail) {
        if (statusPanel) statusPanel.setAttribute('data-state', state);
        if (statusIcon) statusIcon.textContent = icon;
        if (statusLabel) statusLabel.textContent = label;
        if (statusDetail) statusDetail.textContent = detail || '';
    }

    function setProgress(percent) {
        if (progressFill) progressFill.style.width = percent + '%';
    }

    // Cerrar panel de estado
    if (statusClose) {
        statusClose.addEventListener('click', function () {
            hideStatusPanel();
        });
    }

    // =============================================
    // UI: Bloquear / desbloquear botón
    // =============================================
    function lockButton() {
        btnActualizar.disabled = true;
        btnActualizar.classList.add('loading');
        btnActualizar.textContent = '⏳ Procesando...';
    }

    function unlockButton() {
        btnActualizar.disabled = false;
        btnActualizar.classList.remove('loading');
        btnActualizar.textContent = '🔄 Actualizar Paneles';
    }

    // =============================================
    // Toast de notificación
    // =============================================
    function showToast(message, type) {
        var toast = document.getElementById('toast');
        if (!toast) return;
        toast.textContent = message;
        toast.className = 'toast ' + type;
        setTimeout(function () {
            toast.classList.add('hidden');
        }, 5000);
    }

});
