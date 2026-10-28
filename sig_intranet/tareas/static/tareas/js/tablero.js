/* ============================================================
   MÓDULO TAREAS - Tablero de objetivos (burbujas)
   ------------------------------------------------------------
   Versión productiva: los datos vienen de la API (/tareas/api/...),
   se persisten en el servidor y se sincronizan entre usuarios por
   polling. La privacidad y los permisos se validan en el servidor;
   acá solo se usan para la UI. Las burbujas se dibujan con un overlay
   HTML/CSS (vidrio + líquido animado) sincronizado con Cytoscape.
   ============================================================ */
(function () {
  'use strict';

  var SCRIPT = document.currentScript;

  // ----- Config desde el <script> (data-*) -----
  var TABLERO_URL, VERSION_URL, CSRF, API_BASE;

  // ----- Estado -----
  var USERS = [];
  var DATA = { bubbles: [] };
  var currentUser = null;
  var positions = {};
  var cy = null;
  var overlays = {};
  var openBubbleId = null;
  var modalOkHandler = null;
  var lastVersion = -1;
  var panelSortBy = 'manual', panelGroupBy = 'none';
  var posTimers = {};
  // Filtros de visualización del lienzo (solo UI; no tocan los datos)
  var filtros = { responsable: '', estado: '', ocultarCompletadas: false };
  // Zonas por dueño: cada usuario tiene una región del lienzo
  var zonasOn = leerPref('tb_zonas', true);
  var zonas = {};

  function leerPref(clave, porDefecto) {
    try {
      var v = window.localStorage.getItem(clave);
      return v === null ? porDefecto : v === '1';
    } catch (e) { return porDefecto; }
  }
  function guardarPref(clave, valor) {
    try { window.localStorage.setItem(clave, valor ? '1' : '0'); } catch (e) { /* modo privado */ }
  }

  // ----- API -----
  function readConfig() {
    TABLERO_URL = SCRIPT.getAttribute('data-tablero-url');
    VERSION_URL = SCRIPT.getAttribute('data-version-url');
    CSRF = SCRIPT.getAttribute('data-csrf-token');
    API_BASE = TABLERO_URL.replace(/tablero\/?$/, '');
  }
  function apiGet(url) {
    return fetch(url, { credentials: 'same-origin' }).then(function (r) { return r.json(); });
  }
  function apiPost(path, body) {
    return fetch(API_BASE + path, {
      method: 'POST',
      headers: { 'X-CSRFToken': CSRF, 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify(body || {})
    }).then(function (r) {
      return r.json().then(function (j) { return { ok: r.ok, j: j }; },
                           function () { return { ok: r.ok, j: {} }; });
    });
  }
  function pk(id) { return String(id).replace(/^[a-z]+/, ''); }

  function cargarTablero() {
    return apiGet(TABLERO_URL).then(function (res) {
      if (!res.success) throw new Error(res.message || 'No se pudo cargar.');
      var d = res.data;
      USERS = d.usuarios || [];
      currentUser = d.yo;
      lastVersion = d.version;
      DATA = { bubbles: d.objetivos || [] };
      positions = {};
      DATA.bubbles.forEach(function (o) { if (o.pos) positions[o.id] = { x: o.pos.x, y: o.pos.y }; });
    });
  }
  function recargar() {
    return cargarTablero().then(function () {
      render();
      if (openBubbleId) { var b = getBubble(openBubbleId); if (b) renderPanel(b); else closePanel(); }
    });
  }
  // Acciones estructurales: POST y recarga del tablero
  function persistReload(p, okMsg) {
    return p.then(function (res) {
      if (res.ok && res.j && res.j.success) {
        if (res.j.data && res.j.data.version != null) lastVersion = res.j.data.version;
        if (okMsg) toast(okMsg, 'success');
        return recargar();
      }
      toast((res.j && res.j.message) || 'No se pudo completar la acción.', 'error');
      return recargar();
    }, function () { toast('Error de conexión.', 'error'); });
  }
  // Acciones ágiles (optimistas): ya se aplicaron localmente; solo persisten
  function persistQuiet(p) {
    return p.then(function (res) {
      if (res.ok && res.j && res.j.success) {
        if (res.j.data && res.j.data.version != null) lastVersion = res.j.data.version;
        // El servidor reabrió una tarea recurrente: el estado local quedó obsoleto
        if (res.j.data && res.j.data.reabierta) {
          toast('Tarea recurrente reabierta con el siguiente vencimiento.', 'success');
          return recargar();
        }
      } else {
        toast((res.j && res.j.message) || 'No se pudo guardar.', 'error');
        recargar();
      }
    }, function () { toast('Error de conexión.', 'error'); recargar(); });
  }

  // ----- Utilidades -----
  function userName(id) {
    var u = USERS.find(function (x) { return x.id === id; });
    return u ? u.nombre : 'sin asignar';
  }
  function escapeHtml(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function getBubble(id) { return DATA.bubbles.find(function (b) { return b.id === id; }); }
  function findTask(id) {
    for (var i = 0; i < DATA.bubbles.length; i++) {
      var t = DATA.bubbles[i].tasks.find(function (x) { return x.id === id; });
      if (t) return { bubble: DATA.bubbles[i], task: t };
    }
    return null;
  }
  function findSubtask(id) {
    for (var i = 0; i < DATA.bubbles.length; i++) {
      var b = DATA.bubbles[i];
      for (var j = 0; j < b.tasks.length; j++) {
        var st = (b.tasks[j].subtasks || []).find(function (x) { return x.id === id; });
        if (st) return { bubble: b, task: b.tasks[j], sub: st };
      }
    }
    return null;
  }

  // ----- Reglas (para render y UX; el servidor es autoritativo) -----
  function bubbleWeight(b) {
    var w = 0;
    b.tasks.forEach(function (t) { w += 1 + (t.subtasks ? t.subtasks.length * 0.1 : 0); });
    return w;
  }
  function taskCompleted(t) {
    if (t.subtasks && t.subtasks.length) return t.subtasks.every(function (s) { return s.state === 'completado'; });
    return t.state === 'completado';
  }
  function completedWeight(b) {
    var w = 0;
    b.tasks.forEach(function (t) {
      (t.subtasks || []).forEach(function (s) { if (s.state === 'completado') w += 0.1; });
      if (taskCompleted(t)) w += 1;
    });
    return w;
  }
  function bubblePct(b) {
    var tot = bubbleWeight(b);
    if (tot <= 0) return 0;
    return Math.round((completedWeight(b) / tot) * 100);
  }
  function bubbleCompleted(b) {
    return b.tasks.length > 0 && b.tasks.every(function (t) { return taskCompleted(t); });
  }
  function hasUnmetBlocking(item) {
    return (item.dependsOn || []).some(function (d) { return d.blocking && !d.cumplida; });
  }
  function effTaskState(t) {
    if (hasUnmetBlocking(t)) return 'bloqueado';
    if (taskCompleted(t)) return 'completado';
    var subs = t.subtasks || [];
    if (subs.length && subs.some(function (s) { return s.state === 'completado'; })) return 'en_curso';
    return t.state;
  }
  function effSubState(st) { return st.state; }

  function bubbleMembers(b) {
    var map = {};
    map[b.ownerId] = 'dueño';
    b.tasks.forEach(function (t) {
      if (t.assignee && !map[t.assignee]) map[t.assignee] = 'responsable';
      (t.subtasks || []).forEach(function (s) { if (s.assignee && !map[s.assignee]) map[s.assignee] = 'responsable'; });
    });
    (b.viewers || []).forEach(function (v) {
      if (!map[v.uid] || map[v.uid] === 'responsable') map[v.uid] = (v.perm === 'editar' ? 'invitado·editar' : 'invitado·ver');
    });
    return map;
  }
  function isOwner(b) { return b.ownerId === currentUser; }
  function canEdit(b) {
    if (isOwner(b)) return true;
    var v = (b.viewers || []).find(function (x) { return x.uid === currentUser; });
    return !!(v && v.perm === 'editar');
  }
  function canComplete(b, assignee) { return currentUser === assignee || currentUser === b.ownerId; }

  // ----- Filtros de visualización -----
  function hayFiltros() {
    return !!(filtros.responsable || filtros.estado || filtros.ocultarCompletadas);
  }
  function taskPasaFiltro(t) {
    if (filtros.responsable && t.assignee !== filtros.responsable &&
        !(t.subtasks || []).some(function (s) { return s.assignee === filtros.responsable; })) return false;
    var es = effTaskState(t);
    if (filtros.estado && es !== filtros.estado) return false;
    if (filtros.ocultarCompletadas && es === 'completado') return false;
    return true;
  }
  function bubbleVisible(b) {
    if (!hayFiltros()) return true;
    if (!b.tasks.length) return true;
    return b.tasks.some(taskPasaFiltro);
  }
  function bubblesVisibles() { return DATA.bubbles.filter(bubbleVisible); }

  // ----- Visual de la burbuja -----
  function bubbleState(b) {
    var states = b.tasks.map(effTaskState);
    if (states.indexOf('bloqueado') >= 0) return 'bloqueado';
    if (bubbleCompleted(b)) return 'completado';
    if (states.indexOf('en_curso') >= 0 || states.indexOf('completado') >= 0) return 'en_curso';
    return 'pendiente';
  }
  function stateClass(s) {
    return { pendiente: 'pendiente', en_curso: 'encurso', completado: 'completado', bloqueado: 'bloqueado' }[s] || 'pendiente';
  }
  function stateLabel(s) {
    return { pendiente: 'Pendiente', en_curso: 'En curso', completado: 'Completado', bloqueado: 'Bloqueado' }[s] || s;
  }
  // Crecimiento de la burbuja según su peso (tareas x1 + subtareas x0,1)
  var SIZE_BASE = 60, SIZE_FACTOR = 70;
  function bubbleSize(b) { return Math.round(SIZE_BASE + SIZE_FACTOR * Math.sqrt(bubbleWeight(b))); }

  // ----- Elementos del grafo -----
  function buildElements() {
    var els = [];
    var visibles = bubblesVisibles();
    var visibleIds = {};
    visibles.forEach(function (b) { visibleIds[b.id] = true; });
    visibles.forEach(function (b) {
      els.push({ group: 'nodes', data: { id: b.id, size: bubbleSize(b), weight: bubbleWeight(b), owner: b.ownerId }, classes: 'bubble' });
    });
    var edgeSeen = {};
    var ghostN = 0;
    visibles.forEach(function (b) {
      b.tasks.forEach(function (t) {
        (t.dependsOn || []).forEach(function (dep) {
          if (dep.privado) {
            ghostN += 1;
            var gid = 'ghost_' + b.id + '_' + ghostN;
            els.push({ group: 'nodes', data: { id: gid, label: 'Tarea privada\n' + dep.pct + '%', src: b.id }, classes: 'ghost' });
            els.push({ group: 'edges', data: { id: 'ge_' + gid, source: b.id, target: gid }, classes: 'priv' });
          } else if (dep.targetBubbleId && dep.targetBubbleId !== b.id && visibleIds[dep.targetBubbleId]) {
            var key = b.id + '>' + dep.targetBubbleId;
            if (edgeSeen[key]) { if (dep.blocking) edgeSeen[key].blocking = true; return; }
            var e = { group: 'edges', data: { id: 'e_' + key, source: b.id, target: dep.targetBubbleId }, blocking: dep.blocking };
            edgeSeen[key] = e; els.push(e);
          }
        });
      });
    });
    els.forEach(function (e) {
      if (e.group === 'edges' && e.blocking) e.classes = (e.classes ? e.classes + ' ' : '') + 'block';
    });
    return els;
  }

  var STYLE = [
    { selector: 'node.bubble', style: {
      'width': 'data(size)', 'height': 'data(size)',
      'background-opacity': 0, 'border-width': 0, 'overlay-opacity': 0, 'label': ''
    }},
    { selector: 'node.ghost', style: {
      'shape': 'round-rectangle', 'width': 108, 'height': 42, 'label': 'data(label)',
      'text-wrap': 'wrap', 'text-max-width': 96, 'font-size': 9, 'text-valign': 'center',
      'color': '#ecdcfb', 'background-color': '#3a2550', 'background-opacity': 0.82,
      'border-width': 1.5, 'border-color': '#b98fdc', 'border-style': 'dashed', 'overlay-opacity': 0
    }},
    { selector: 'edge', style: {
      'curve-style': 'bezier', 'target-arrow-shape': 'triangle', 'width': 2,
      'line-color': 'rgba(176,198,214,0.55)', 'target-arrow-color': 'rgba(176,198,214,0.6)',
      'line-style': 'dashed', 'arrow-scale': 1.1
    }},
    { selector: 'edge.block', style: {
      'line-color': '#ff5a4d', 'target-arrow-color': '#ff5a4d', 'width': 3.5, 'line-style': 'solid'
    }},
    { selector: 'edge.priv', style: {
      'line-color': '#c7a3e6', 'target-arrow-color': '#c7a3e6', 'line-style': 'dotted',
      'width': 2, 'target-arrow-shape': 'none'
    }}
  ];

  // ----- Zonas por dueño -----
  var ZONA_W = 900, ZONA_H = 650, ZONA_GAP = 70, ZONA_PAD = 26;
  var zoneEls = {};

  function calcularZonas() {
    zonas = {};
    // Sobre TODAS las burbujas, no las filtradas: si no, la geometría cambiaría
    // al filtrar y las posiciones guardadas quedarían fuera de su zona.
    var duenos = [];
    DATA.bubbles.forEach(function (b) { if (duenos.indexOf(b.ownerId) < 0) duenos.push(b.ownerId); });
    duenos.sort(function (a, b) { return userName(a).localeCompare(userName(b)); });
    var cols = Math.max(1, Math.ceil(Math.sqrt(duenos.length)));
    duenos.forEach(function (uid, i) {
      zonas[uid] = {
        x: (i % cols) * (ZONA_W + ZONA_GAP),
        y: Math.floor(i / cols) * (ZONA_H + ZONA_GAP),
        w: ZONA_W, h: ZONA_H, label: userName(uid)
      };
    });
  }
  function clampAZona(b, pos) {
    var z = zonas[b.ownerId];
    if (!zonasOn || !z) return pos;
    var r = bubbleSize(b) / 2 + ZONA_PAD;
    function eje(valor, inicio, largo) {
      var lo = inicio + r, hi = inicio + largo - r;
      if (lo > hi) return inicio + largo / 2;  // la burbuja es más grande que la zona
      return Math.min(Math.max(valor, lo), hi);
    }
    return { x: eje(pos.x, z.x, z.w), y: eje(pos.y, z.y, z.h) };
  }
  function dentroDeZona(b, pos) {
    var c = clampAZona(b, pos);
    return Math.abs(c.x - pos.x) < 0.5 && Math.abs(c.y - pos.y) < 0.5;
  }
  function applyZoneLayout() {
    var porDueno = {};
    cy.nodes('.bubble').forEach(function (n) {
      var b = getBubble(n.id());
      if (b) (porDueno[b.ownerId] = porDueno[b.ownerId] || []).push(n);
    });
    Object.keys(porDueno).forEach(function (uid) {
      var z = zonas[uid];
      if (!z) return;
      var arr = porDueno[uid].sort(function (a, b) { return (b.data('weight') || 0) - (a.data('weight') || 0); });
      // La celda nunca debe ser menor que la burbuja más grande del dueño
      var maxSize = Math.max.apply(null, arr.map(function (n) { return n.data('size') || 80; }));
      var colsCaben = Math.max(1, Math.floor(z.w / (maxSize + 10)));
      var cols = Math.min(Math.max(1, Math.ceil(Math.sqrt(arr.length))), colsCaben);
      var filas = Math.ceil(arr.length / cols);
      var cw = z.w / cols, ch = Math.max((z.h - ZONA_PAD) / filas, maxSize + 10);
      arr.forEach(function (n, i) {
        n.position({
          x: z.x + cw * ((i % cols) + 0.5),
          y: z.y + ZONA_PAD + ch * (Math.floor(i / cols) + 0.5)
        });
      });
    });
  }
  function createZones() {
    zoneEls = {};
    if (!zonasOn) return;
    var layer = document.getElementById('tb-overlay-layer');
    Object.keys(zonas).forEach(function (uid) {
      var el = document.createElement('div');
      el.className = 'tb-zone';
      el.innerHTML = '<span class="tb-zone-label">' + escapeHtml(zonas[uid].label) + '</span>';
      layer.appendChild(el);
      zoneEls[uid] = el;
    });
  }
  function syncZones() {
    if (!cy) return;
    var zoom = cy.zoom(), pan = cy.pan();
    Object.keys(zoneEls).forEach(function (uid) {
      var z = zonas[uid], s = zoneEls[uid].style;
      s.left = (z.x * zoom + pan.x) + 'px';
      s.top = (z.y * zoom + pan.y) + 'px';
      s.width = (z.w * zoom) + 'px';
      s.height = (z.h * zoom) + 'px';
      s.fontSize = Math.max(9, 16 * zoom).toFixed(1) + 'px';
    });
  }

  function applyAutoLayout() {
    var arr = cy.nodes('.bubble').toArray().sort(function (a, b) { return (b.data('weight') || 0) - (a.data('weight') || 0); });
    if (!arr.length) return;
    var maxSize = Math.max.apply(null, arr.map(function (n) { return n.data('size') || 80; }));
    var baseR = Math.max(250, maxSize * 1.85);
    arr[0].position({ x: 0, y: 0 });
    var rest = arr.slice(1), i = 0, ring = 1;
    while (i < rest.length) {
      var count = Math.min(ring * 6, rest.length - i);
      var radius = ring * baseR;
      for (var k = 0; k < count; k++) {
        var ang = (2 * Math.PI * k / count) - Math.PI / 2;
        rest[i + k].position({ x: radius * Math.cos(ang), y: radius * Math.sin(ang) });
      }
      i += count; ring += 1;
    }
  }

  function positionGhosts() {
    if (!cy) return;
    var counters = {};
    cy.nodes('.ghost').forEach(function (g) {
      var src = cy.getElementById(g.data('src'));
      if (!src || src.empty()) return;
      counters[g.data('src')] = (counters[g.data('src')] || 0) + 1;
      var p = src.position();
      g.position({ x: p.x + 165, y: p.y + 58 * counters[g.data('src')] });
    });
  }

  // ----- Overlay de burbujas -----
  function createOverlays() {
    var layer = document.getElementById('tb-overlay-layer');
    layer.innerHTML = '';
    overlays = {};
    createZones();
    cy.nodes('.bubble').forEach(function (n) {
      var b = getBubble(n.id());
      if (!b) return;
      var pct = bubblePct(b);
      var node = document.createElement('div');
      node.className = 'bubble-node st-' + stateClass(bubbleState(b)) + (openBubbleId === b.id ? ' selected' : '');
      node.innerHTML =
        '<div class="bubble-glass">' +
          '<div class="bubble-liquid"></div>' +
          '<div class="bubble-gloss"></div>' +
          (b.private ? '<div class="bubble-priv">Privada</div>' : '') +
          '<div class="bubble-label"><span class="ttl">' + escapeHtml(b.title) + '</span><span class="pct">' + pct + '%</span></div>' +
        '</div>';
      layer.appendChild(node);
      var liquid = node.querySelector('.bubble-liquid');
      overlays[b.id] = { el: node, liquid: liquid, label: node.querySelector('.bubble-label'),
        ttl: node.querySelector('.ttl'), pctEl: node.querySelector('.pct') };
      requestAnimationFrame(function () { liquid.style.height = pct + '%'; });
    });
    syncOverlays();
  }
  function syncOverlays() {
    if (!cy) return;
    syncZones();
    cy.nodes('.bubble').forEach(function (n) {
      var ov = overlays[n.id()];
      if (!ov) return;
      var p = n.renderedPosition(), w = n.renderedWidth();
      var s = ov.el.style;
      s.left = p.x + 'px'; s.top = p.y + 'px'; s.width = w + 'px'; s.height = w + 'px';
      ov.label.style.fontSize = Math.max(8, Math.min(18, w * 0.125)).toFixed(1) + 'px';
    });
  }
  function updateOverlayVisual(b) {
    var ov = overlays[b.id];
    if (!ov) return;
    var pct = bubblePct(b);
    ov.el.className = 'bubble-node st-' + stateClass(bubbleState(b)) + (openBubbleId === b.id ? ' selected' : '');
    ov.liquid.style.height = pct + '%';
    ov.pctEl.textContent = pct + '%';
    ov.ttl.textContent = b.title;
  }
  function setSelectedOverlay() {
    Object.keys(overlays).forEach(function (id) {
      overlays[id].el.classList.toggle('selected', id === openBubbleId);
    });
  }

  // ----- Render -----
  function render() {
    poblarFiltroResponsables();
    var container = document.getElementById('cy');
    var prevPan = cy ? cy.pan() : null;
    var prevZoom = cy ? cy.zoom() : null;
    if (cy) { cy.destroy(); cy = null; }

    cy = cytoscape({
      container: container, elements: buildElements(), style: STYLE,
      wheelSensitivity: 0.2, minZoom: 0.25, maxZoom: 2.5, boxSelectionEnabled: false
    });

    calcularZonas();
    if (zonasOn) applyZoneLayout(); else applyAutoLayout();
    cy.nodes('.bubble').forEach(function (n) {
      var p = positions[n.id()], b = getBubble(n.id());
      // Si la posición guardada es de un layout anterior y cae fuera de la zona
      // del dueño, se ignora y queda la que calculó applyZoneLayout.
      if (p && b && (!zonasOn || dentroDeZona(b, p))) n.position(p);
    });
    cy.nodes('.ghost').forEach(function (g) { g.ungrabify(); });
    positionGhosts();
    createOverlays();

    cy.on('render', syncOverlays);
    cy.on('tap', 'node.bubble', function (e) { openPanel(e.target.id()); });
    cy.on('tap', 'node.ghost', function () { toast('Pertenece a una burbuja privada que no puedes ver.', 'error'); });
    cy.on('tap', function (e) { if (e.target === cy) closePanel(); });
    cy.on('dragfree', 'node.bubble', function (e) {
      var n = e.target, b = getBubble(n.id());
      if (b) n.position(clampAZona(b, { x: n.position('x'), y: n.position('y') }));
      positions[n.id()] = { x: n.position('x'), y: n.position('y') };
      positionGhosts(); syncOverlays();
      guardarPosicion(n.id(), n.position('x'), n.position('y'));
    });

    if (prevPan && prevZoom) { cy.zoom(prevZoom); cy.pan(prevPan); }
    else { cy.resize(); cy.fit(undefined, 60); }
    syncOverlays();

    if (openBubbleId) {
      var abierta = getBubble(openBubbleId);
      if (!abierta || !bubbleVisible(abierta)) closePanel();
    }
  }
  function refreshAllVisuals() {
    DATA.bubbles.forEach(function (b) { if (overlays[b.id]) updateOverlayVisual(b); });
  }
  function guardarPosicion(oid, x, y) {
    if (posTimers[oid]) clearTimeout(posTimers[oid]);
    posTimers[oid] = setTimeout(function () {
      apiPost('objetivo/' + pk(oid) + '/posicion/', { x: x, y: y });
    }, 400);
  }

  // ----- Panel lateral -----
  var panel = document.getElementById('panel-lateral');
  var overlay = document.getElementById('tb-overlay');
  var plTitulo = document.getElementById('pl-titulo-wrap');
  var plCuerpo = document.getElementById('pl-cuerpo');

  function openPanel(bid) {
    var b = getBubble(bid);
    if (!b) return;
    openBubbleId = bid;
    renderPanel(b);
    panel.classList.remove('is-hidden');
    panel.setAttribute('aria-hidden', 'false');
    overlay.classList.remove('is-hidden');
    setSelectedOverlay();
  }
  function closePanel() {
    openBubbleId = null;
    panel.classList.add('is-hidden');
    panel.setAttribute('aria-hidden', 'true');
    overlay.classList.add('is-hidden');
    setSelectedOverlay();
  }

  function stateChip(s) { return '<span class="tb-state ' + s + '">' + stateLabel(s) + '</span>'; }
  function recurLabel(r) {
    return { diaria: 'Diaria', semanal: 'Semanal', mensual: 'Mensual' }[r] || '';
  }
  function recurChip(r) {
    return r ? '<span class="tb-recur" title="Al completarla se reabre con el siguiente vencimiento">&#8635; ' + recurLabel(r) + '</span>' : '';
  }
  function prioChip(p) { return p ? '<span class="tb-prio ' + p + '">' + p.charAt(0).toUpperCase() + p.slice(1) + '</span>' : ''; }

  function depsHtml(item, editable) {
    if (!item.dependsOn || !item.dependsOn.length) return '';
    var html = '<div class="tb-deps">Depende de: ';
    item.dependsOn.forEach(function (d) {
      var name = d.privado ? ('Tarea privada (' + d.pct + '%)') : (d.nombre || 'desconocido');
      var cls = (d.privado ? ' priv' : '') + (d.blocking ? ' block' : '');
      var met = d.cumplida ? ' · cumplida' : (d.blocking ? ' · pendiente' : '');
      html += '<span class="tb-dep-pill' + cls + '">' + (d.blocking ? 'Bloqueante: ' : '') + escapeHtml(name) + met +
        (editable && d.depId ? ' <span class="rm" data-act="del-dep" data-id="' + d.depId + '" title="Quitar">&times;</span>' : '') +
        '</span>';
    });
    return html + '</div>';
  }

  function sortTasksList(list, by) {
    if (by === 'manual') return list.slice();
    var arr = list.slice();
    if (by === 'prioridad') { var r = { alta: 0, media: 1, baja: 2 }; arr.sort(function (a, b) { return (r[a.prio] == null ? 9 : r[a.prio]) - (r[b.prio] == null ? 9 : r[b.prio]); }); }
    else if (by === 'estado') { var r2 = { bloqueado: 0, en_curso: 1, pendiente: 2, completado: 3 }; arr.sort(function (a, b) { return r2[effTaskState(a)] - r2[effTaskState(b)]; }); }
    else if (by === 'responsable') { arr.sort(function (a, b) { return userName(a.assignee).localeCompare(userName(b.assignee)); }); }
    else if (by === 'fecha') { arr.sort(function (a, b) { return (a.due || '9999-99-99').localeCompare(b.due || '9999-99-99'); }); }
    return arr;
  }
  function buildTaskGroups(b) {
    if (panelGroupBy === 'none') return [{ label: null, tasks: sortTasksList(b.tasks, panelSortBy) }];
    var buckets = {}, order = [];
    b.tasks.forEach(function (t) {
      var key, label;
      if (panelGroupBy === 'estado') { var s = effTaskState(t); key = s; label = stateLabel(s); }
      else if (panelGroupBy === 'responsable') { key = t.assignee; label = userName(t.assignee); }
      else { key = t.prio || 'sin'; label = 'Prioridad ' + (t.prio || 'sin definir'); }
      if (!buckets[key]) { buckets[key] = { label: label, tasks: [] }; order.push(key); }
      buckets[key].tasks.push(t);
    });
    return order.map(function (k) { return { label: buckets[k].label, tasks: sortTasksList(buckets[k].tasks, panelSortBy) }; });
  }
  function selOptions(list, sel) {
    return list.map(function (o) { return '<option value="' + o[0] + '"' + (o[0] === sel ? ' selected' : '') + '>' + o[1] + '</option>'; }).join('');
  }

  function renderTaskCard(b, t, showOrder, idx, total) {
    var editable = canEdit(b);
    var es = effTaskState(t);
    var hasSubs = t.subtasks && t.subtasks.length;
    var done = taskCompleted(t);
    var blocked = es === 'bloqueado';
    var canC = canComplete(b, t.assignee) && !blocked;
    var cbDisabled = hasSubs || !canC;
    var cbTitle = hasSubs ? 'Se completa al terminar sus subtareas'
      : (blocked ? 'Bloqueada por una dependencia pendiente'
        : (canComplete(b, t.assignee) ? 'Marcar completada' : 'Solo el responsable o el dueño'));

    var h = '<div class="tb-task"><div class="tb-task-head">';
    if (showOrder && editable) {
      h += '<span class="tb-ord">' +
        '<button data-act="task-up" data-id="' + t.id + '"' + (idx === 0 ? ' disabled' : '') + ' title="Subir">&#9650;</button>' +
        '<button data-act="task-down" data-id="' + t.id + '"' + (idx === total - 1 ? ' disabled' : '') + ' title="Bajar">&#9660;</button>' +
        '</span>';
    }
    h += '<input type="checkbox" class="tb-check" data-act="toggle-task" data-id="' + t.id + '"' +
      (done ? ' checked' : '') + (cbDisabled ? ' disabled' : '') + ' title="' + cbTitle + '">' +
      '<div class="tb-task-main">' +
        '<div class="tb-task-title ' + (done ? 'done' : '') + '">' + escapeHtml(t.title) + '</div>' +
        '<div class="tb-task-sub">' + stateChip(es) + prioChip(t.prio) + recurChip(t.recur) +
          '<span class="tb-assignee">Resp.: ' + escapeHtml(userName(t.assignee)) + '</span>' +
          (t.due ? '<span class="tb-assignee">Vence: ' + escapeHtml(t.due) + '</span>' : '') +
        '</div>' + depsHtml(t, editable);

    if (hasSubs) {
      h += '<div class="tb-subtasks">';
      t.subtasks.forEach(function (s, si) {
        var sdone = s.state === 'completado';
        var scanC = canComplete(b, s.assignee);
        h += '<div class="tb-subtask">';
        if (editable) {
          h += '<span class="tb-ord">' +
            '<button data-act="sub-up" data-id="' + s.id + '"' + (si === 0 ? ' disabled' : '') + ' title="Subir">&#9650;</button>' +
            '<button data-act="sub-down" data-id="' + s.id + '"' + (si === t.subtasks.length - 1 ? ' disabled' : '') + ' title="Bajar">&#9660;</button>' +
            '</span>';
        }
        h += '<input type="checkbox" class="tb-check" data-act="toggle-sub" data-id="' + s.id + '"' +
            (sdone ? ' checked' : '') + (scanC ? '' : ' disabled') + '>' +
          '<div style="flex:1">' +
            '<div class="tb-subtask-title ' + (sdone ? 'done' : '') + '">' + escapeHtml(s.title) +
              ' <span class="tb-assignee">Resp.: ' + escapeHtml(userName(s.assignee)) + '</span></div>' +
          '</div>' +
          (editable ? '<button class="tb-btn tb-btn-sm" data-act="edit-sub" data-id="' + s.id + '">Editar</button>' : '') +
          (editable ? '<button class="tb-btn tb-btn-sm tb-btn-danger" data-act="del-sub" data-id="' + s.id + '"' +
            (isOwner(b) ? '' : ' disabled title="Solo el dueño"') + '>Quitar</button>' : '') +
        '</div>';
      });
      h += '</div>';
    }
    if (editable) {
      h += '<div class="tb-task-actions">' +
        '<button class="tb-btn tb-btn-sm" data-act="edit-task" data-id="' + t.id + '">Editar</button>' +
        '<button class="tb-btn tb-btn-sm" data-act="add-sub" data-id="' + t.id + '">Agregar subtarea</button>' +
        '<button class="tb-btn tb-btn-sm" data-act="add-dep" data-id="' + t.id + '">Dependencia</button>' +
        '<button class="tb-btn tb-btn-sm tb-btn-danger" data-act="del-task" data-id="' + t.id + '"' +
          (isOwner(b) ? '' : ' disabled title="Solo el dueño elimina"') + '>Eliminar</button>' +
      '</div>';
    }
    return h + '</div></div>';
  }

  function renderPanel(b) {
    var editable = canEdit(b);
    var members = bubbleMembers(b);
    var memberIds = Object.keys(members);
    var pct = bubblePct(b);
    var w = bubbleWeight(b);

    plTitulo.innerHTML =
      '<h2>' + escapeHtml(b.title) + '</h2>' +
      '<div class="tb-meta-row">' +
        '<span class="tb-chip ' + (b.private ? 'priv' : 'pub') + '">' + (b.private ? 'Privada' : 'Pública') + '</span>' +
        '<span class="tb-chip">Peso ' + w.toFixed(1) + '</span>' +
        '<span class="tb-chip">' + b.tasks.length + ' tareas</span>' +
        '<span class="tb-chip">' + memberIds.length + ' usuarios</span>' +
        '<span class="tb-chip">Dueño: ' + escapeHtml(userName(b.ownerId)) + '</span>' +
      '</div>';

    var html = '';
    if (b.private) {
      html += '<div class="tb-priv-note">Burbuja privada. Solo la ven sus miembros. ' +
        'Al agregar a alguien, pasa a ver todo su contenido.</div>';
    }
    html += '<div class="tb-progress"><span style="width:' + pct + '%"></span></div>' +
      '<div class="tb-progress-label">' + pct + '% completado' + (bubbleCompleted(b) ? ' · objetivo cumplido' : '') + '</div>';

    html += '<div class="tb-section-title">Tareas' +
      (editable ? '<button class="tb-btn tb-btn-sm" data-act="add-task">Agregar tarea</button>' : '') + '</div>';
    html += '<div class="tb-tasks-controls">' +
      '<span class="tb-mini">Ordenar <select data-act="set-sort">' +
        selOptions([['manual', 'Manual'], ['prioridad', 'Prioridad'], ['estado', 'Estado'], ['responsable', 'Responsable'], ['fecha', 'Fecha límite']], panelSortBy) +
      '</select></span>' +
      '<span class="tb-mini">Agrupar <select data-act="set-group">' +
        selOptions([['none', 'Sin agrupar'], ['estado', 'Estado'], ['responsable', 'Responsable'], ['prioridad', 'Prioridad']], panelGroupBy) +
      '</select></span>' +
    '</div>';

    var showOrder = (panelSortBy === 'manual' && panelGroupBy === 'none');
    var groups = buildTaskGroups(b);
    if (!b.tasks.length) html += '<div class="tb-empty">Sin tareas todavía.</div>';
    groups.forEach(function (g) {
      if (g.label !== null) html += '<div class="tb-group-head">' + escapeHtml(g.label) + '<span class="count">' + g.tasks.length + '</span></div>';
      g.tasks.forEach(function (t, i) { html += renderTaskCard(b, t, showOrder, i, g.tasks.length); });
    });

    html += '<div class="tb-section-title">Usuarios de la burbuja</div><div>';
    memberIds.forEach(function (uid) {
      var role = members[uid];
      var isInvited = role.indexOf('invitado') === 0;
      html += '<span class="tb-member">' + escapeHtml(userName(uid)) +
        ' <span class="role">(' + role + ')</span>' +
        (isInvited && editable ? ' <span class="rm" data-act="rm-member" data-id="' + uid + '" title="Quitar">&times;</span>' : '') +
        '</span>';
    });
    html += '</div>';
    if (editable) html += '<div class="tb-task-actions"><button class="tb-btn tb-btn-sm" data-act="add-member">Agregar usuario</button></div>';

    html += '<div class="tb-section-title">Objetivo</div><div class="tb-task-actions">';
    if (isOwner(b)) {
      html += '<button class="tb-btn tb-btn-sm" data-act="complete-bubble">Marcar completado</button>';
      html += '<button class="tb-btn tb-btn-sm" data-act="toggle-priv">' + (b.private ? 'Hacer pública' : 'Hacer privada') + '</button>';
      html += '<button class="tb-btn tb-btn-sm tb-btn-danger" data-act="del-bubble">Eliminar objetivo</button>';
    }
    html += '</div>';
    if (!editable) {
      html += '<div class="tb-hint" style="margin-top:12px">Estás viendo como <b>' + escapeHtml(userName(currentUser)) +
        '</b>, que no tiene permiso de edición en esta burbuja.</div>';
    }

    plCuerpo.innerHTML = html;
    wirePanel(b);
  }

  function wirePanel(b) {
    plCuerpo.querySelectorAll('[data-act]').forEach(function (el) {
      var act = el.getAttribute('data-act'), id = el.getAttribute('data-id');
      var evt = (el.tagName === 'INPUT' || el.tagName === 'SELECT') ? 'change' : 'click';
      el.addEventListener(evt, function () { handleAction(b, act, id, el); });
    });
  }

  function arrMove(arr, id, dir) {
    var i = arr.findIndex(function (x) { return x.id === id; });
    if (i < 0) return;
    var j = i + dir;
    if (j < 0 || j >= arr.length) return;
    var tmp = arr[i]; arr[i] = arr[j]; arr[j] = tmp;
  }

  function handleAction(b, act, id, el) {
    switch (act) {
      case 'set-sort': panelSortBy = el.value; renderPanel(b); break;
      case 'set-group': panelGroupBy = el.value; renderPanel(b); break;
      case 'task-up':
      case 'task-down':
        arrMove(b.tasks, id, act === 'task-up' ? -1 : 1);
        renderPanel(b); refreshAllVisuals();
        persistQuiet(apiPost('objetivo/' + pk(b.id) + '/reordenar-tareas/', { orden: b.tasks.map(function (t) { return pk(t.id); }) }));
        break;
      case 'sub-up':
      case 'sub-down': {
        var fu = findSubtask(id);
        if (fu) {
          arrMove(fu.task.subtasks, id, act === 'sub-up' ? -1 : 1);
          renderPanel(b);
          persistQuiet(apiPost('tarea/' + pk(fu.task.id) + '/reordenar-subtareas/', { orden: fu.task.subtasks.map(function (s) { return pk(s.id); }) }));
        }
        break;
      }
      case 'toggle-task': {
        var t = b.tasks.find(function (x) { return x.id === id; });
        if (!t) return;
        if (hasUnmetBlocking(t)) { toast('Tarea bloqueada por una dependencia pendiente.', 'error'); el.checked = false; return; }
        if (!canComplete(b, t.assignee)) { toast('Solo el responsable o el dueño pueden completarla.', 'error'); el.checked = !el.checked; return; }
        t.state = el.checked ? 'completado' : 'pendiente';
        refreshAllVisuals(); renderPanel(b);
        persistQuiet(apiPost('tarea/' + pk(t.id) + '/actualizar/', { estado: t.state }));
        break;
      }
      case 'toggle-sub': {
        var fs = findSubtask(id);
        if (!fs) return;
        if (!canComplete(b, fs.sub.assignee)) { toast('Solo el responsable o el dueño pueden completarla.', 'error'); el.checked = !el.checked; return; }
        fs.sub.state = el.checked ? 'completado' : 'pendiente';
        if (fs.task.subtasks.every(function (s) { return s.state === 'completado'; })) fs.task.state = 'completado';
        else if (fs.task.state === 'completado') fs.task.state = 'en_curso';
        refreshAllVisuals(); renderPanel(b);
        persistQuiet(apiPost('subtarea/' + pk(id) + '/actualizar/', { estado: fs.sub.state }));
        break;
      }
      case 'complete-bubble': {
        if (!isOwner(b)) { toast('Solo el dueño.', 'error'); return; }
        b.tasks.forEach(function (t) { t.state = 'completado'; (t.subtasks || []).forEach(function (s) { s.state = 'completado'; }); });
        refreshAllVisuals(); renderPanel(b); toast('Objetivo marcado como completado.', 'success');
        persistQuiet(apiPost('objetivo/' + pk(b.id) + '/completar/', {}));
        break;
      }
      case 'toggle-priv':
        if (!isOwner(b)) return;
        persistReload(apiPost('objetivo/' + pk(b.id) + '/actualizar/', { es_privada: !b.private }),
                      b.private ? 'Burbuja ahora pública.' : 'Burbuja ahora privada.');
        break;
      case 'del-bubble':
        if (!isOwner(b)) return;
        if (!confirm('¿Eliminar el objetivo "' + b.title + '" y todas sus tareas?')) return;
        persistReload(apiPost('objetivo/' + pk(b.id) + '/eliminar/', {}), 'Objetivo eliminado.');
        break;
      case 'del-task':
        if (!isOwner(b)) { toast('Solo el dueño elimina.', 'error'); return; }
        persistReload(apiPost('tarea/' + pk(id) + '/eliminar/', {}), 'Tarea eliminada.');
        break;
      case 'del-sub':
        if (!isOwner(b)) { toast('Solo el dueño elimina.', 'error'); return; }
        persistReload(apiPost('subtarea/' + pk(id) + '/eliminar/', {}), 'Subtarea eliminada.');
        break;
      case 'del-dep':
        persistReload(apiPost('dependencia/' + id + '/eliminar/', {}), 'Dependencia eliminada.');
        break;
      case 'edit-task': modalEditTask(b, id); break;
      case 'edit-sub': modalEditSub(b, id); break;
      case 'add-task': modalAddTask(b); break;
      case 'add-sub': modalAddSub(b, id); break;
      case 'add-dep': modalAddDep(b, id); break;
      case 'add-member': modalAddMember(b); break;
      case 'rm-member':
        persistReload(apiPost('objetivo/' + pk(b.id) + '/miembro/', { accion: 'quitar', usuario: id }), 'Usuario quitado.');
        break;
    }
  }

  // ----- Modales -----
  function userOptions(sel) {
    return USERS.map(function (u) { return '<option value="' + u.id + '"' + (u.id === sel ? ' selected' : '') + '>' + escapeHtml(u.nombre) + '</option>'; }).join('');
  }
  function modalAddTask(b) {
    openModal('Nueva tarea en "' + b.title + '"',
      '<div class="tb-field"><label>Título</label><input type="text" id="m-title" placeholder="Describe la tarea"></div>' +
      '<div class="tb-field"><label>Responsable</label><select id="m-assignee">' + userOptions(currentUser) + '</select></div>' +
      '<div class="tb-field"><label>Prioridad</label><select id="m-prio"><option value="alta">Alta</option><option value="media" selected>Media</option><option value="baja">Baja</option></select></div>' +
      '<div class="tb-field"><label>Fecha límite</label><input type="date" id="m-due"></div>' +
      '<div class="tb-field"><label>Recurrencia</label><select id="m-recur">' + recurOptions('') + '</select></div>',
      function () {
        var title = document.getElementById('m-title').value.trim();
        if (!title) { toast('Escribe un título.', 'error'); return false; }
        persistReload(apiPost('objetivo/' + pk(b.id) + '/tarea/crear/', {
          titulo: title, responsable: document.getElementById('m-assignee').value,
          prioridad: document.getElementById('m-prio').value, vence: document.getElementById('m-due').value || '',
          recurrencia: document.getElementById('m-recur').value
        }), 'Tarea agregada.');
      });
  }
  function recurOptions(sel) {
    return [['', 'No recurrente'], ['diaria', 'Diaria'], ['semanal', 'Semanal'], ['mensual', 'Mensual']]
      .map(function (o) { return '<option value="' + o[0] + '"' + (o[0] === (sel || '') ? ' selected' : '') + '>' + o[1] + '</option>'; })
      .join('');
  }
  function modalEditTask(b, taskId) {
    var t = b.tasks.find(function (x) { return x.id === taskId; });
    if (!t) return;
    openModal('Editar tarea',
      '<div class="tb-field"><label>Título</label><input type="text" id="m-title" value="' + escapeHtml(t.title) + '"></div>' +
      '<div class="tb-field"><label>Responsable</label><select id="m-assignee">' + userOptions(t.assignee) + '</select></div>' +
      '<div class="tb-field"><label>Prioridad</label><select id="m-prio">' +
        selOptions([['alta', 'Alta'], ['media', 'Media'], ['baja', 'Baja']], t.prio) + '</select></div>' +
      '<div class="tb-field"><label>Fecha límite</label><input type="date" id="m-due" value="' + escapeHtml(t.due || '') + '"></div>' +
      '<div class="tb-field"><label>Recurrencia</label><select id="m-recur">' + recurOptions(t.recur) + '</select>' +
      '<div class="tb-hint">Al completarla vuelve a pendiente con el siguiente vencimiento.</div></div>',
      function () {
        var title = document.getElementById('m-title').value.trim();
        if (!title) { toast('Escribe un título.', 'error'); return false; }
        persistReload(apiPost('tarea/' + pk(t.id) + '/actualizar/', {
          titulo: title, responsable: document.getElementById('m-assignee').value,
          prioridad: document.getElementById('m-prio').value,
          vence: document.getElementById('m-due').value || '',
          recurrencia: document.getElementById('m-recur').value
        }), 'Tarea actualizada.');
      });
  }
  function modalEditSub(b, subId) {
    var fs = findSubtask(subId);
    if (!fs) return;
    openModal('Editar subtarea',
      '<div class="tb-field"><label>Título</label><input type="text" id="m-title" value="' + escapeHtml(fs.sub.title) + '"></div>' +
      '<div class="tb-field"><label>Responsable</label><select id="m-assignee">' + userOptions(fs.sub.assignee) + '</select></div>',
      function () {
        var title = document.getElementById('m-title').value.trim();
        if (!title) { toast('Escribe un título.', 'error'); return false; }
        persistReload(apiPost('subtarea/' + pk(subId) + '/actualizar/', {
          titulo: title, responsable: document.getElementById('m-assignee').value
        }), 'Subtarea actualizada.');
      });
  }
  function modalAddSub(b, taskId) {
    var t = b.tasks.find(function (x) { return x.id === taskId; });
    if (!t) return;
    openModal('Nueva subtarea en "' + t.title + '"',
      '<div class="tb-field"><label>Título</label><input type="text" id="m-title" placeholder="Describe la subtarea"></div>' +
      '<div class="tb-field"><label>Responsable</label><select id="m-assignee">' + userOptions(t.assignee) + '</select>' +
      '<div class="tb-hint">Puede ser distinto al responsable de la tarea.</div></div>',
      function () {
        var title = document.getElementById('m-title').value.trim();
        if (!title) { toast('Escribe un título.', 'error'); return false; }
        persistReload(apiPost('tarea/' + pk(t.id) + '/subtarea/crear/', {
          titulo: title, responsable: document.getElementById('m-assignee').value
        }), 'Subtarea agregada.');
      });
  }
  function modalAddMember(b) {
    openModal('Agregar usuario a "' + b.title + '"',
      '<div class="tb-field"><label>Usuario</label><select id="m-user">' + userOptions(null) + '</select></div>' +
      '<div class="tb-field"><label>Permiso</label><select id="m-perm"><option value="ver">Solo visualizar</option><option value="editar">Editar</option></select>' +
      (b.private ? '<div class="tb-hint">Esta burbuja es privada: el usuario podrá ver todo su contenido.</div>' : '') + '</div>',
      function () {
        persistReload(apiPost('objetivo/' + pk(b.id) + '/miembro/', {
          accion: 'agregar', usuario: document.getElementById('m-user').value, permiso: document.getElementById('m-perm').value
        }), 'Usuario agregado.');
      });
  }
  function modalAddDep(b, taskId) {
    var t = b.tasks.find(function (x) { return x.id === taskId; });
    if (!t) return;
    var opts = '<optgroup label="Burbujas">';
    DATA.bubbles.forEach(function (ob) { if (ob.id !== b.id) opts += '<option value="bubble:' + ob.id + '">' + escapeHtml(ob.title) + '</option>'; });
    opts += '</optgroup><optgroup label="Tareas">';
    DATA.bubbles.forEach(function (ob) {
      ob.tasks.forEach(function (ot) { if (ot.id !== t.id) opts += '<option value="task:' + ot.id + '">' + escapeHtml(ot.title) + ' — ' + escapeHtml(ob.title) + '</option>'; });
    });
    opts += '</optgroup><optgroup label="Subtareas de esta burbuja">';
    b.tasks.forEach(function (ot) { (ot.subtasks || []).forEach(function (s) { opts += '<option value="subtask:' + s.id + '">' + escapeHtml(s.title) + ' — ' + escapeHtml(ot.title) + '</option>'; }); });
    opts += '</optgroup>';
    openModal('Dependencia de "' + t.title + '"',
      '<div class="tb-field"><label>Depende de</label><select id="m-dep">' + opts + '</select></div>' +
      '<div class="tb-field"><label class="tb-check-inline"><input type="checkbox" id="m-block"> Es bloqueante (no se puede completar hasta que la otra esté lista)</label></div>',
      function () {
        var val = document.getElementById('m-dep').value;
        if (!val) { toast('Elige un objetivo.', 'error'); return false; }
        var parts = val.split(':');
        persistReload(apiPost('tarea/' + pk(t.id) + '/dependencia/crear/', {
          targetType: parts[0], targetId: parts[1], blocking: document.getElementById('m-block').checked
        }), 'Dependencia agregada.');
      });
  }

  // ----- Modal genérico -----
  var modal = document.getElementById('tb-modal');
  var modalTitle = document.getElementById('tb-modal-title');
  var modalBody = document.getElementById('tb-modal-body');
  function openModal(title, bodyHtml, onOk, okLabel, ancha) {
    document.getElementById('tb-modal-ok').textContent = okLabel || 'Guardar';
    document.getElementById('tb-modal-cancel').style.display = okLabel ? 'none' : '';
    modal.querySelector('.tb-modal-card').classList.toggle('ancha', !!ancha);
    modalTitle.textContent = title;
    modalBody.innerHTML = bodyHtml;
    modalOkHandler = onOk;
    modal.classList.remove('is-hidden');
    var first = modalBody.querySelector('input,select,textarea');
    if (first) setTimeout(function () { first.focus(); }, 30);
  }
  function closeModal() { modal.classList.add('is-hidden'); modalOkHandler = null; }
  document.getElementById('tb-modal-ok').addEventListener('click', function () {
    if (modalOkHandler) { if (modalOkHandler() === false) return; }
    closeModal();
  });
  document.getElementById('tb-modal-cancel').addEventListener('click', closeModal);
  document.getElementById('tb-modal-close').addEventListener('click', closeModal);

  // ----- Toast -----
  var toastEl = document.getElementById('toast');
  var toastTimer = null;
  function toast(msg, type) {
    toastEl.textContent = msg;
    toastEl.className = 'toast ' + (type || 'success');
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toastEl.className = 'toast ' + (type || 'success') + ' hidden'; }, 2600);
  }

  // ----- Nuevo objetivo -----
  function modalNewBubble() {
    openModal('Nuevo objetivo',
      '<div class="tb-field"><label>Título del objetivo</label><input type="text" id="m-title" placeholder="Ej: Migración de correo"></div>' +
      '<div class="tb-field"><label class="tb-check-inline"><input type="checkbox" id="m-priv"> Privada (solo tú y quienes invites)</label></div>' +
      '<div class="tb-hint">Serás el dueño. Podrás agregar tareas, usuarios y dependencias.</div>',
      function () {
        var title = document.getElementById('m-title').value.trim();
        if (!title) { toast('Escribe un título.', 'error'); return false; }
        var priv = document.getElementById('m-priv').checked;
        apiPost('objetivo/crear/', { titulo: title, es_privada: priv }).then(function (res) {
          if (res.ok && res.j && res.j.success) {
            if (res.j.data && res.j.data.version != null) lastVersion = res.j.data.version;
            toast('Objetivo creado.', 'success');
            cargarTablero().then(function () { render(); if (res.j.data && res.j.data.id) openPanel(res.j.data.id); });
          } else { toast((res.j && res.j.message) || 'No se pudo crear.', 'error'); }
        }, function () { toast('Error de conexión.', 'error'); });
      });
  }

  // ----- Resumen por usuario -----
  function resumenPorUsuario() {
    // Fecha LOCAL en formato AAAA-MM-DD: toISOString() daría UTC y de noche
    // (Chile UTC-3/-4) contaría como vencidas las que vencen hoy.
    var hoy = new Date().toLocaleDateString('sv-SE');
    var filas = {};
    function fila(uid) {
      if (!filas[uid]) filas[uid] = { uid: uid, pendiente: 0, en_curso: 0, completado: 0, bloqueado: 0, vencidas: 0, total: 0 };
      return filas[uid];
    }
    DATA.bubbles.forEach(function (b) {
      b.tasks.forEach(function (t) {
        var f = fila(t.assignee);
        var es = effTaskState(t);
        f[es] = (f[es] || 0) + 1;
        f.total += 1;
        if (t.due && t.due < hoy && es !== 'completado') f.vencidas += 1;
        (t.subtasks || []).forEach(function (s) {
          var fs = fila(s.assignee);
          fs[s.state] = (fs[s.state] || 0) + 1;
          fs.total += 1;
        });
      });
    });
    return Object.keys(filas).map(function (k) { return filas[k]; })
      .sort(function (a, b) { return userName(a.uid).localeCompare(userName(b.uid)); });
  }
  function modalResumen() {
    var filas = resumenPorUsuario();
    var html;
    if (!filas.length) {
      html = '<div class="tb-empty">No hay tareas asignadas.</div>';
    } else {
      html = '<table class="tb-resumen"><thead><tr>' +
        '<th>Usuario</th><th class="num">Total</th><th class="num">Pendientes</th><th class="num">En curso</th>' +
        '<th class="num">Bloqueadas</th><th class="num">Completadas</th><th class="num">Vencidas</th></tr></thead><tbody>';
      filas.forEach(function (f) {
        html += '<tr>' +
          '<td>' + escapeHtml(userName(f.uid)) + '</td>' +
          '<td class="num">' + f.total + '</td>' +
          '<td class="num">' + f.pendiente + '</td>' +
          '<td class="num">' + f.en_curso + '</td>' +
          '<td class="num">' + f.bloqueado + '</td>' +
          '<td class="num">' + f.completado + '</td>' +
          '<td class="num' + (f.vencidas ? ' alerta' : '') + '">' + f.vencidas + '</td>' +
        '</tr>';
      });
      html += '</tbody></table>' +
        '<div class="tb-hint">Cuenta tareas y subtareas de las burbujas que puedes ver. ' +
        'Vencidas: con fecha límite pasada y sin completar.</div>';
    }
    openModal('Resumen de tareas por usuario', html, null, 'Cerrar', true);
  }

  // ----- Filtros de la barra -----
  function poblarFiltroResponsables() {
    var sel = document.getElementById('f-resp');
    if (!sel) return;
    var actual = filtros.responsable;
    sel.innerHTML = '<option value="">Todos los responsables</option>' +
      USERS.map(function (u) {
        return '<option value="' + u.id + '"' + (u.id === actual ? ' selected' : '') + '>' + escapeHtml(u.nombre) + '</option>';
      }).join('');
  }
  function reubicarYPersistir(msg) {
    positions = {};
    render();
    cy.nodes('.bubble').forEach(function (n) { guardarPosicion(n.id(), n.position('x'), n.position('y')); });
    if (msg) toast(msg, 'success');
  }

  // ----- Toolbar -----
  function sincronizarBotonZonas() {
    var btn = document.getElementById('btn-zonas');
    if (!btn) return;
    btn.textContent = zonasOn ? 'Zonas: sí' : 'Zonas: no';
    btn.classList.toggle('tb-btn-on', zonasOn);
  }
  // Al filtrar cambia la geometría del lienzo: reencuadrar para no dejar al
  // usuario mirando una zona que ahora está vacía.
  function aplicarFiltro() {
    render();
    if (cy) { cy.fit(undefined, 60); syncOverlays(); }
  }

  function wireToolbar() {
    sincronizarBotonZonas();
    document.getElementById('btn-nuevo-objetivo').addEventListener('click', modalNewBubble);
    document.getElementById('btn-reordenar').addEventListener('click', function () {
      // Reacomoda (por zona de dueño, o por peso si las zonas están apagadas)
      reubicarYPersistir(zonasOn ? 'Reordenado por zona de dueño.' : 'Reordenado por peso (la más grande al centro).');
    });
    document.getElementById('btn-ajustar').addEventListener('click', function () { if (cy) { cy.fit(undefined, 60); syncOverlays(); } });
    document.getElementById('btn-resumen').addEventListener('click', modalResumen);
    document.getElementById('btn-zonas').addEventListener('click', function () {
      zonasOn = !zonasOn;
      guardarPref('tb_zonas', zonasOn);
      sincronizarBotonZonas();
      reubicarYPersistir(zonasOn ? 'Burbujas agrupadas en la zona de su dueño.' : 'Zonas desactivadas.');
    });
    document.getElementById('f-resp').addEventListener('change', function () {
      filtros.responsable = this.value; aplicarFiltro();
    });
    document.getElementById('f-estado').addEventListener('change', function () {
      filtros.estado = this.value; aplicarFiltro();
    });
    document.getElementById('f-completadas').addEventListener('change', function () {
      filtros.ocultarCompletadas = this.checked; aplicarFiltro();
    });
    document.getElementById('pl-cerrar').addEventListener('click', closePanel);
    overlay.addEventListener('click', closePanel);
    document.getElementById('btn-legend-toggle').addEventListener('click', function () {
      var lg = document.getElementById('tb-legend');
      lg.classList.toggle('collapsed');
      this.textContent = lg.classList.contains('collapsed') ? '+' : '–';
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { if (!modal.classList.contains('is-hidden')) closeModal(); else closePanel(); }
    });
  }

  // ----- Polling (tiempo real) -----
  function iniciarPolling() {
    var sync = document.getElementById('tb-sync');
    if (sync) { sync.classList.add('live'); sync.textContent = 'Sincronización en vivo'; }
    setInterval(function () {
      apiGet(VERSION_URL).then(function (res) {
        if (res && res.success && res.data && res.data.version !== lastVersion) {
          lastVersion = res.data.version;
          recargar();
        }
      }).catch(function () {});
    }, 5000);
  }

  // ----- Arranque -----
  function init() {
    if (typeof cytoscape === 'undefined') {
      document.getElementById('cy').innerHTML =
        '<div style="padding:40px;text-align:center;color:#ffd3cd;font-family:sans-serif">' +
        'No se pudo cargar Cytoscape.js. Revisa que /static esté disponible.</div>';
      return;
    }
    readConfig();
    wireToolbar();
    cargarTablero().then(function () {
      render();
      var reajustar = function () { if (cy) { cy.resize(); cy.fit(undefined, 60); syncOverlays(); } };
      // Reajusta cuando el layout ya se asentó (el contenedor flex puede
      // terminar de dimensionarse después del primer render).
      requestAnimationFrame(function () { requestAnimationFrame(reajustar); });
      setTimeout(reajustar, 150);
      // Y ante cualquier cambio de tamaño del lienzo (carga, resize, nav que envuelve).
      if (window.ResizeObserver) {
        var ro = new ResizeObserver(function () { if (cy) { cy.resize(); syncOverlays(); } });
        ro.observe(document.getElementById('cy'));
      }
      iniciarPolling();
    }, function () {
      document.getElementById('cy').innerHTML =
        '<div style="padding:40px;text-align:center;color:#ffd3cd;font-family:sans-serif">No se pudo cargar el tablero.</div>';
    });
    window.addEventListener('resize', function () { if (cy) { cy.resize(); syncOverlays(); } });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
