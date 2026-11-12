(function () {
  'use strict';

  var form = document.getElementById('orden-form');
  if (!form) return;

  var store = { antes: [], despues: [] };
  var MAX_LADO = 1600;
  var CALIDAD = 0.82;

  /* ----------------------------- proyecto ----------------------------- */
  var sel = document.getElementById('project_id');
  var site = document.getElementById('site');
  var rack = document.getElementById('rack');
  var dest = document.getElementById('destinatarios');

  function syncProject() {
    var op = sel.options[sel.selectedIndex];
    if (!op || !op.value) {
      dest.textContent = '';
      return;
    }
    if (site && !site.value && op.dataset.site) site.value = op.dataset.site;
    if (rack && !rack.value && op.dataset.racks) {
      rack.value = op.dataset.racks.split(',')[0].trim();
    }
    dest.textContent = op.dataset.recipients
      ? 'Se enviará a: ' + op.dataset.recipients
      : 'Este proyecto no tiene destinatarios configurados.';
  }
  if (sel) {
    sel.addEventListener('change', syncProject);
    syncProject();
  }

  /* ------------------------------ fotos ------------------------------ */
  function cargarImagen(src) {
    return new Promise(function (resolve, reject) {
      var img = new Image();
      img.onload = function () { resolve(img); };
      img.onerror = reject;
      img.src = src;
    });
  }

  function comprimir(file) {
    var url = URL.createObjectURL(file);
    return cargarImagen(url).then(function (img) {
      var escala = Math.min(1, MAX_LADO / Math.max(img.width, img.height));
      var canvas = document.createElement('canvas');
      canvas.width = Math.round(img.width * escala);
      canvas.height = Math.round(img.height * escala);
      canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(url);
      return new Promise(function (resolve, reject) {
        canvas.toBlob(function (blob) {
          if (!blob) return reject(new Error('No se pudo procesar la imagen'));
          var nombre = (file.name || 'foto').replace(/\.[^.]+$/, '') + '.jpg';
          resolve(new File([blob], nombre, { type: 'image/jpeg' }));
        }, 'image/jpeg', CALIDAD);
      });
    }, function (err) {
      URL.revokeObjectURL(url);
      throw err;
    });
  }

  function pintar(kind) {
    var caja = document.getElementById('thumbs-' + kind);
    var contador = document.getElementById('count-' + kind);
    if (!caja) return;
    caja.innerHTML = '';
    store[kind].forEach(function (file, i) {
      var div = document.createElement('div');
      div.className = 'thumb';
      var img = document.createElement('img');
      var url = URL.createObjectURL(file);
      img.src = url;
      img.alt = 'Foto ' + (i + 1);
      var boton = document.createElement('button');
      boton.type = 'button';
      boton.setAttribute('aria-label', 'Quitar foto');
      boton.textContent = '\u00d7';
      boton.addEventListener('click', function () {
        URL.revokeObjectURL(url);
        store[kind].splice(i, 1);
        pintar(kind);
      });
      div.appendChild(img);
      div.appendChild(boton);
      caja.appendChild(div);
    });
    if (contador) contador.textContent = store[kind].length;
  }

  Array.prototype.forEach.call(
    form.querySelectorAll('input[type="file"][data-kind]'),
    function (input) {
      input.addEventListener('change', function () {
        var kind = input.dataset.kind;
        var archivos = Array.prototype.slice.call(input.files || []);
        input.value = '';
        archivos.reduce(function (cadena, file) {
          return cadena.then(function () {
            return comprimir(file).then(function (comprimido) {
              store[kind].push(comprimido);
            }).catch(function () { /* archivo no válido */ });
          });
        }, Promise.resolve()).then(function () { pintar(kind); });
      });
    }
  );

  /* ------------------------------ firma ------------------------------ */
  var canvas = document.getElementById('firma');
  var ctx = canvas ? canvas.getContext('2d') : null;
  var dibujando = false;
  var conTinta = false;

  function dimensionar() {
    if (!canvas) return;
    var dpr = window.devicePixelRatio || 1;
    var rect = canvas.getBoundingClientRect();
    canvas.width = Math.round(rect.width * dpr);
    canvas.height = Math.round(rect.height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, rect.width, rect.height);
    ctx.lineWidth = 2;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.strokeStyle = '#0f172a';
  }

  function punto(e) {
    var r = canvas.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  }

  if (canvas) {
    dimensionar();
    window.addEventListener('resize', function () {
      if (!conTinta) dimensionar();
    });

    canvas.addEventListener('pointerdown', function (e) {
      e.preventDefault();
      dibujando = true;
      conTinta = true;
      if (canvas.setPointerCapture) canvas.setPointerCapture(e.pointerId);
      var p = punto(e);
      ctx.beginPath();
      ctx.moveTo(p.x, p.y);
      ctx.lineTo(p.x + 0.1, p.y);
      ctx.stroke();
    });

    canvas.addEventListener('pointermove', function (e) {
      if (!dibujando) return;
      e.preventDefault();
      var p = punto(e);
      ctx.lineTo(p.x, p.y);
      ctx.stroke();
    });

    ['pointerup', 'pointercancel', 'pointerleave'].forEach(function (ev) {
      canvas.addEventListener(ev, function () { dibujando = false; });
    });

    var limpiar = document.getElementById('limpiar-firma');
    if (limpiar) {
      limpiar.addEventListener('click', function () {
        conTinta = false;
        dimensionar();
      });
    }
  }

  /* ------------------------------ envío ------------------------------ */
  function mostrarError(texto) {
    quitarError();
    var div = document.createElement('div');
    div.className = 'flash error';
    div.id = 'error-envio';
    div.textContent = texto;
    form.parentNode.insertBefore(div, form);
    div.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  function quitarError() {
    var previo = document.getElementById('error-envio');
    if (previo) previo.remove();
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    quitarError();

    var trabajo = form.querySelector('textarea[name="work"]');
    if (!trabajo || trabajo.value.trim().length < 10) {
      mostrarError('Describe el trabajo realizado (mínimo 10 caracteres).');
      return;
    }
    if (store.antes.length + store.despues.length === 0) {
      mostrarError('Agrega al menos una foto del trabajo realizado.');
      return;
    }
    if (!sel.value) {
      mostrarError('Selecciona el proyecto o cliente.');
      return;
    }

    var boton = document.getElementById('btn-enviar');
    var textoOriginal = boton.textContent;
    boton.disabled = true;
    boton.textContent = 'Enviando orden…';

    var datos = new FormData(form);
    datos.set('firma', conTinta && canvas ? canvas.toDataURL('image/png') : '');
    store.antes.forEach(function (f) { datos.append('photos_antes', f, f.name); });
    store.despues.forEach(function (f) { datos.append('photos_despues', f, f.name); });

    fetch(form.action, {
      method: 'POST',
      body: datos,
      headers: {
        'X-Requested-With': 'XMLHttpRequest',
        'Accept': 'application/json'
      },
      credentials: 'same-origin'
    }).then(function (resp) {
      return resp.json().catch(function () { return {}; }).then(function (data) {
        if (!resp.ok || !data.ok) {
          throw new Error(data.error || 'No se pudo guardar la orden.');
        }
        return data;
      });
    }).then(function (data) {
      window.location.href = data.redirect;
    }).catch(function (err) {
      boton.disabled = false;
      boton.textContent = textoOriginal;
      mostrarError(err.message || 'Error de conexión. Intenta nuevamente.');
    });
  });
})();
