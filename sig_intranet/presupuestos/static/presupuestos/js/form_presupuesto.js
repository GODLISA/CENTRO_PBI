/**
 * Formulario de nuevo presupuesto.
 * - Al elegir un área carga su matriz de cobros vía API interna.
 * - Permite agregar líneas desde la matriz o manuales.
 * - Calcula totales referenciales en vivo (el cálculo definitivo es del backend).
 */
(function () {
    'use strict';

    var script = document.currentScript;
    // Las plantillas traen las URLs reversadas con id=0; se reemplaza por el id real
    var ITEMS_URL_PLANTILLA = script.dataset.itemsUrlPlantilla;
    var COMUNAS_URL_PLANTILLA = script.dataset.comunasUrlPlantilla;

    var selArea = document.getElementById('sel-area');
    var selZona = document.getElementById('sel-zona');
    var selComuna = document.getElementById('sel-comuna');
    var inpKm = document.getElementById('inp-km');
    var tabla = document.getElementById('tabla-lineas');
    var cuerpo = document.getElementById('cuerpo-lineas');
    var acciones = document.getElementById('acciones-lineas');
    var resumen = document.getElementById('resumen');
    var ayuda = document.getElementById('ayuda-items');
    var form = document.getElementById('form-presupuesto');

    var matriz = [];          // ítems del área seleccionada
    var parametros = {};      // {UF: '39000.5', IVA: '19'}
    var valoresKm = {};       // {'global': '850', '<zonaId>': '900'}

    // ---------- Carga de matriz por área ----------
    selArea.addEventListener('change', function () {
        cuerpo.innerHTML = '';
        if (!selArea.value) {
            tabla.style.display = 'none';
            acciones.style.display = 'none';
            resumen.style.display = 'none';
            ayuda.style.display = '';
            return;
        }
        fetch(ITEMS_URL_PLANTILLA.replace('/0/', '/' + selArea.value + '/'))
            .then(function (r) { return r.json(); })
            .then(function (data) {
                matriz = data.items;
                parametros = data.parametros;
                valoresKm = data.valores_km;
                ayuda.style.display = 'none';
                tabla.style.display = '';
                acciones.style.display = '';
                resumen.style.display = '';
                if (parametros.IVA) {
                    document.getElementById('res-iva-pct').textContent = parseFloat(parametros.IVA);
                }
                if (matriz.length) { agregarFilaItem(); }
                recalcular();
            });
    });

    // ---------- Filas ----------
    document.getElementById('btn-agregar-item').addEventListener('click', agregarFilaItem);
    document.getElementById('btn-agregar-manual').addEventListener('click', agregarFilaManual);

    function agregarFilaItem() {
        if (!matriz.length) {
            alert('El área seleccionada no tiene ítems en su matriz de cobros. Agréguelos en el admin o use una línea manual.');
            return;
        }
        var tr = document.createElement('tr');
        tr.dataset.tipo = 'item';

        var opciones = matriz.map(function (i) {
            var precio = i.moneda === 'UF' ? i.precio_unitario + ' UF' : fmtCLP(i.precio_unitario);
            return '<option value="' + i.id + '">' + esc(i.concepto) + ' (' + precio + '/' + esc(i.unidad) + ')</option>';
        }).join('');

        tr.innerHTML =
            '<td><select class="sel-item">' + opciones + '</select></td>' +
            '<td class="celda-unidad"></td>' +
            '<td class="celda-moneda"></td>' +
            '<td class="num celda-precio"></td>' +
            '<td><input type="number" class="num inp-cantidad" min="0.01" step="0.01" value="1"></td>' +
            '<td class="num celda-total">$0</td>' +
            '<td><button type="button" class="btn-quitar" title="Quitar línea">✕</button></td>';

        cuerpo.appendChild(tr);
        tr.querySelector('.sel-item').addEventListener('change', function () { refrescarFilaItem(tr); });
        conectarFila(tr);
        refrescarFilaItem(tr);
    }

    function agregarFilaManual() {
        var tr = document.createElement('tr');
        tr.dataset.tipo = 'manual';
        tr.innerHTML =
            '<td><input type="text" class="inp-concepto" placeholder="Concepto (línea manual)"></td>' +
            '<td><input type="text" class="inp-unidad" value="unidad"></td>' +
            '<td><select class="sel-moneda"><option value="CLP">CLP</option><option value="UF">UF</option></select></td>' +
            '<td><input type="number" class="num inp-precio" min="0" step="0.0001" value="0"></td>' +
            '<td><input type="number" class="num inp-cantidad" min="0.01" step="0.01" value="1"></td>' +
            '<td class="num celda-total">$0</td>' +
            '<td><button type="button" class="btn-quitar" title="Quitar línea">✕</button></td>';
        cuerpo.appendChild(tr);
        conectarFila(tr);
    }

    function conectarFila(tr) {
        tr.querySelector('.btn-quitar').addEventListener('click', function () {
            tr.remove();
            recalcular();
        });
        tr.querySelectorAll('input, select').forEach(function (el) {
            el.addEventListener('input', recalcular);
            el.addEventListener('change', recalcular);
        });
    }

    function refrescarFilaItem(tr) {
        var item = buscarItem(tr.querySelector('.sel-item').value);
        if (!item) return;
        tr.querySelector('.celda-unidad').textContent = item.unidad;
        tr.querySelector('.celda-moneda').textContent = item.moneda;
        tr.querySelector('.celda-precio').textContent =
            item.moneda === 'UF' ? item.precio_unitario + ' UF' : fmtCLP(item.precio_unitario);
        recalcular();
    }

    function buscarItem(id) {
        return matriz.find(function (i) { return String(i.id) === String(id); });
    }

    // ---------- Comunas por zona (autocompleta km ida + regreso) ----------
    var comunas = [];

    selZona.addEventListener('change', function () {
        comunas = [];
        selComuna.innerHTML = '<option value="">-- Sin comuna --</option>';
        if (!selZona.value) {
            selComuna.disabled = true;
            selComuna.innerHTML = '<option value="">-- Seleccione una zona primero --</option>';
            recalcular();
            return;
        }
        fetch(COMUNAS_URL_PLANTILLA.replace('/0/', '/' + selZona.value + '/'))
            .then(function (r) { return r.json(); })
            .then(function (data) {
                comunas = data.comunas;
                comunas.forEach(function (c) {
                    var etiqueta = c.nombre + (c.region ? ' (' + c.region + ')' : '');
                    selComuna.insertAdjacentHTML(
                        'beforeend',
                        '<option value="' + c.id + '">' + esc(etiqueta) + '</option>'
                    );
                });
                selComuna.disabled = false;
                recalcular();
            });
    });

    selComuna.addEventListener('change', function () {
        var comuna = comunas.find(function (c) { return String(c.id) === selComuna.value; });
        if (comuna) {
            inpKm.value = parseFloat(comuna.km) || 0;
        }
        recalcular();
    });

    // ---------- Cálculo referencial ----------
    inpKm.addEventListener('input', recalcular);

    function precioCLP(precio, moneda) {
        var p = parseFloat(precio) || 0;
        if (moneda === 'UF') {
            var uf = parseFloat(parametros.UF);
            if (!uf) return NaN; // UF no disponible
            return p * uf;
        }
        return p;
    }

    function recalcular() {
        var subtotal = 0;
        var hayUFSinValor = false;

        cuerpo.querySelectorAll('tr').forEach(function (tr) {
            var cantidad = parseFloat(tr.querySelector('.inp-cantidad').value) || 0;
            var precio, moneda;

            if (tr.dataset.tipo === 'item') {
                var item = buscarItem(tr.querySelector('.sel-item').value);
                if (!item) return;
                precio = item.precio_unitario;
                moneda = item.moneda;
            } else {
                precio = tr.querySelector('.inp-precio').value;
                moneda = tr.querySelector('.sel-moneda').value;
            }

            var clp = precioCLP(precio, moneda);
            if (isNaN(clp)) {
                hayUFSinValor = true;
                tr.querySelector('.celda-total').textContent = '(sin UF)';
                return;
            }
            var total = Math.round(clp) * cantidad;
            subtotal += total;
            tr.querySelector('.celda-total').textContent = fmtCLP(total);
        });

        // Traslado: valor km de la zona o global
        var km = parseFloat(inpKm.value) || 0;
        var valorKm = parseFloat(valoresKm[selZona.value] || valoresKm['global']) || 0;
        var traslado = Math.round(km * valorKm);
        subtotal += traslado;

        var iva = parseFloat(parametros.IVA) || 0;
        var montoIva = Math.round(subtotal * iva / 100);

        document.getElementById('res-traslado').textContent = fmtCLP(traslado);
        document.getElementById('res-subtotal').textContent = fmtCLP(subtotal);
        document.getElementById('res-iva').textContent = fmtCLP(montoIva);
        document.getElementById('res-total').textContent =
            fmtCLP(subtotal + montoIva) + (hayUFSinValor ? ' *' : '');
    }

    // ---------- Envío ----------
    form.addEventListener('submit', function (e) {
        var lineas = [];
        cuerpo.querySelectorAll('tr').forEach(function (tr) {
            var cantidad = tr.querySelector('.inp-cantidad').value;
            if (tr.dataset.tipo === 'item') {
                lineas.push({
                    item_id: parseInt(tr.querySelector('.sel-item').value, 10),
                    cantidad: cantidad
                });
            } else {
                lineas.push({
                    item_id: null,
                    concepto: tr.querySelector('.inp-concepto').value,
                    unidad: tr.querySelector('.inp-unidad').value,
                    moneda: tr.querySelector('.sel-moneda').value,
                    precio_unitario: tr.querySelector('.inp-precio').value,
                    cantidad: cantidad
                });
            }
        });

        if (!lineas.length) {
            e.preventDefault();
            alert('Debe agregar al menos una línea al presupuesto.');
            return;
        }
        document.getElementById('lineas-json').value = JSON.stringify(lineas);
    });

    // ---------- Utilidades ----------
    function fmtCLP(valor) {
        var n = Math.round(parseFloat(valor) || 0);
        return '$' + n.toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    }

    function esc(texto) {
        var div = document.createElement('div');
        div.textContent = texto;
        return div.innerHTML;
    }
})();
