const apiBase = (window.LEOBRICK_API_BASE || '').replace(/\/$/, '');
const fileInput = document.getElementById('fileInput');
const dropzone = document.getElementById('dropzone');
const previewCard = document.getElementById('previewCard');
const previewImage = document.getElementById('previewImage');
const previewName = document.getElementById('previewName');
const removeImageButton = document.getElementById('removeImage');
const generatorForm = document.getElementById('generatorForm');
const submitButton = document.getElementById('submitButton');
const previewButton = document.getElementById('previewButton');
const statusText = document.getElementById('statusText');
const progressWrap = document.getElementById('progressWrap');
const progressBar = document.getElementById('progressBar');
const resultPanel = document.getElementById('resultPanel');
const resultMeta = document.getElementById('resultMeta');
const resultPreviewText = document.getElementById('resultPreviewText');

const publicCodeField = document.getElementById('publicCodeField');
const copyCodeButton = document.getElementById('copyCodeButton');
const paypalSection = document.getElementById('paypalSection');
const paypalButtonsContainer = document.getElementById('paypalButtonsContainer');
const manualConfirmButton = document.getElementById('manualConfirmButton');

const redeemInput = document.getElementById('redeemInput');
const redeemButton = document.getElementById('redeemButton');

const menuButton = document.getElementById('menuButton');
const mobileMenu = document.getElementById('mobileMenu');
const uploadBadge = document.getElementById('uploadBadge');
const buttonLabel = submitButton.querySelector('.button-label');

let currentFile = null;
let progressTimer = null;
let previewObjectUrl = null;
let remotePreviewUrl = null;

let generatedCode = null;

let cropper = null;
let rawFile = null;

const cropModal = document.getElementById('cropModal');
const cropImage = document.getElementById('cropImage');
const cropConfirm = document.getElementById('cropConfirm');
const cropCancel = document.getElementById('cropCancel');

cropCancel.addEventListener('click', () => {
  cropModal.hidden = true;
  if (cropper) {
    cropper.destroy();
    cropper = null;
  }
});

cropConfirm.addEventListener('click', async () => {
  if (!cropper) return;

  const canvas = cropper.getCroppedCanvas({
    fillColor: '#ffffff'
  });

  const blob = await new Promise(res => canvas.toBlob(res, 'image/png'));

  const croppedFile = new File([blob], rawFile.name, {
    type: 'image/png'
  });

  cropModal.hidden = true;

  if (cropper) {
    cropper.destroy();
    cropper = null;
  }

  setPreview(croppedFile);
});

function snapToMultipleOf16(value) {
  if (!Number.isFinite(value) || value < 16) return 16;
  return Math.max(16, Math.round(value / 16) * 16);
}

function studToCm(studs) {
  return (studs * 0.8).toFixed(1);
}

function ensureDimensionMeta(input) {
  let meta = input.parentElement.querySelector('.dimension-meta');
  if (!meta) {
    meta = document.createElement('div');
    meta.className = 'dimension-meta';
    meta.style.fontSize = '12px';
    meta.style.opacity = '0.72';
    meta.style.marginTop = '6px';
    input.parentElement.appendChild(meta);
  }
  return meta;
}

function updateDimensionDisplay(input) {
  const raw = parseInt(input.value, 10);
  const value = snapToMultipleOf16(raw);
  input.value = value;

  const meta = ensureDimensionMeta(input);
  meta.textContent = `${value} stud · ${studToCm(value)} cm`;
}

function initDimensionInputs() {
  const widthInput = generatorForm.querySelector('input[name="width"]');
  const heightInput = generatorForm.querySelector('input[name="height"]');

  [widthInput, heightInput].forEach((input) => {
    if (!input) return;

    input.step = 16;
    updateDimensionDisplay(input);

    input.addEventListener('input', () => {
      const raw = parseInt(input.value, 10);
      const meta = ensureDimensionMeta(input);
      if (!Number.isFinite(raw) || raw < 16) {
        meta.textContent = `16 stud · ${studToCm(16)} cm`;
        return;
      }
      meta.textContent = `${raw} stud · ${studToCm(raw)} cm`;
    });

    input.addEventListener('blur', () => {
      updateDimensionDisplay(input);
    });
  });
}

/* ------------------ HELPERS ------------------ */

async function normalizeImageForUpload(file) {
  const MAX_DIMENSION = 1600; // tipo WhatsApp (aggressivo)
  const MAX_FILE_SIZE = 1.5 * 1024 * 1024; // ~1.5MB
  const OUTPUT_TYPE = 'image/jpeg';

  // -------- EXIF ORIENTATION --------
  async function getOrientation(file) {
    const buffer = await file.arrayBuffer();
    const view = new DataView(buffer);

    if (view.getUint16(0, false) !== 0xFFD8) return -2;

    let offset = 2;
    while (offset < view.byteLength) {
      if (view.getUint16(offset + 2, false) <= 8) return -1;
      const marker = view.getUint16(offset, false);
      offset += 2;

      if (marker === 0xFFE1) {
        if (view.getUint32(offset += 2, false) !== 0x45786966) return -1;

        const little = view.getUint16(offset += 6, false) === 0x4949;
        offset += view.getUint32(offset + 4, little);

        const tags = view.getUint16(offset, little);
        offset += 2;

        for (let i = 0; i < tags; i++) {
          if (view.getUint16(offset + (i * 12), little) === 0x0112) {
            return view.getUint16(offset + (i * 12) + 8, little);
          }
        }
      } else if ((marker & 0xFF00) !== 0xFF00) {
        break;
      } else {
        offset += view.getUint16(offset, false);
      }
    }
    return -1;
  }

  // -------- LOAD IMAGE (SAFE MOBILE) --------
  let img;

  try {
    const bitmap = await createImageBitmap(file);
    img = bitmap;
  } catch (e) {
    img = await new Promise((resolve, reject) => {
      const image = new Image();
      const url = URL.createObjectURL(file);

      image.onload = () => {
        URL.revokeObjectURL(url);
        resolve(image);
      };

      image.onerror = reject;
      image.src = url;
    });
  }

  let width = img.width;
  let height = img.height;

  // -------- RESIZE (WHATSAPP STYLE) --------
  if (Math.max(width, height) > MAX_DIMENSION) {
    const scale = MAX_DIMENSION / Math.max(width, height);
    width = Math.round(width * scale);
    height = Math.round(height * scale);
  }

  const orientation = await getOrientation(file);

  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d', { alpha: false });

  // gestione rotazione
  if (orientation === 6 || orientation === 8) {
    canvas.width = height;
    canvas.height = width;
  } else {
    canvas.width = width;
    canvas.height = height;
  }

  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  // -------- APPLY ORIENTATION --------
  switch (orientation) {
    case 6:
      ctx.rotate(90 * Math.PI / 180);
      ctx.drawImage(img, 0, -height, width, height);
      break;
    case 3:
      ctx.rotate(Math.PI);
      ctx.drawImage(img, -width, -height, width, height);
      break;
    case 8:
      ctx.rotate(-90 * Math.PI / 180);
      ctx.drawImage(img, -width, 0, width, height);
      break;
    default:
      ctx.drawImage(img, 0, 0, width, height);
  }

  // -------- COMPRESSION --------
  let quality = 0.82;
  let blob = await new Promise(res => canvas.toBlob(res, OUTPUT_TYPE, quality));

  while (blob.size > MAX_FILE_SIZE && quality > 0.5) {
    quality -= 0.08;
    blob = await new Promise(res => canvas.toBlob(res, OUTPUT_TYPE, quality));
  }

  console.log("📦 FINAL IMAGE:", {
    width,
    height,
    size: blob.size,
    quality
  });

  return new File(
    [blob],
    file.name.replace(/\.[^.]+$/, '') + '.jpg',
    {
      type: OUTPUT_TYPE,
      lastModified: Date.now()
    }
  );
}

async function apiFetch(url, options = {}, label = 'request') {
  const startedAt = performance.now();

  try {
    const response = await fetch(url, options);

    console.group(`[API ${label}]`);
    console.log('URL:', url);
    console.log('Method:', options.method || 'GET');

    if (options.body instanceof FormData) {
      const file = options.body.get('file');
      if (file) {
        console.log('File:', {
          name: file.name,
          type: file.type,
          size: file.size
        });
      }

      const entries = {};
      for (const [key, value] of options.body.entries()) {
        if (key !== 'file') entries[key] = value;
      }
      console.log('Form fields:', entries);
    }

    console.log('Status:', response.status);
    console.log('Elapsed ms:', Math.round(performance.now() - startedAt));
    console.groupEnd();

    return response;
  } catch (error) {
    console.group(`[API ${label}]`);
    console.error('NETWORK ERROR', {
      url,
      method: options.method || 'GET',
      message: error?.message,
      name: error?.name,
      online: navigator.onLine,
      elapsedMs: Math.round(performance.now() - startedAt)
    });
    console.groupEnd();
    throw error;
  }
}

async function downloadPackage(token) {
  try {
    const response = await fetch(`${apiBase}/api/redeem`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token })
    });

    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || 'Errore durante il download del pacchetto.');
    }

    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'package.zip';
    a.click();

    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) {
    setStatus(error.message || 'Errore durante il download.');
  }
}

/* ------------------ UI INIT ------------------ */

function initHeroPixels() {
  const grid = document.querySelector('.pixel-grid');
  if (!grid) return;
  const palette = ['#ed1c24', '#ff7a00', '#f2b705', '#4385f5', '#c8b889', '#111827', '#e5e7eb'];
  const cells = 16 * 13;
  const fragment = document.createDocumentFragment();
  for (let i = 0; i < cells; i += 1) {
    const px = document.createElement('span');
    const color = palette[Math.floor(Math.random() * palette.length)];
    px.style.background = color;
    px.style.animationDelay = `${(i % 10) * 0.12}s`;
    fragment.appendChild(px);
  }
  grid.appendChild(fragment);
}

function initReveal() {
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.14 });
  document.querySelectorAll('.reveal').forEach((node) => observer.observe(node));
}

/* ------------------ STATE ------------------ */

function updateSubmitState() {
  submitButton.disabled = !currentFile;
  if (previewButton) previewButton.disabled = !currentFile;
  uploadBadge.textContent = currentFile ? 'File pronto' : 'Nessun file';
  uploadBadge.classList.toggle('is-ready', Boolean(currentFile));
}

function setStatus(message) {
  statusText.textContent = message;
}

function setLoadingState(isLoading) {
  submitButton.classList.toggle('is-loading', isLoading);
  submitButton.disabled = isLoading || !currentFile;
  buttonLabel.textContent = isLoading ? 'Generazione in corso' : 'Genera codice';
}

/* ------------------ FILE ------------------ */

async function setPreview(file) {
  try {
	console.log("SET PREVIEW FILE:", file);
    const normalizedFile = await normalizeImageForUpload(file);
    currentFile = normalizedFile;

    if (previewObjectUrl) URL.revokeObjectURL(previewObjectUrl);
    if (remotePreviewUrl) {
      URL.revokeObjectURL(remotePreviewUrl);
      remotePreviewUrl = null;
    }

    previewObjectUrl = URL.createObjectURL(normalizedFile);
    previewImage.src = previewObjectUrl;
    previewName.textContent = file.name;

    previewCard.hidden = false;
    dropzone.classList.add('has-file');

    setStatus(`${file.name} selezionato.`);
    updateSubmitState();
  } catch (error) {
    console.error('Errore durante la normalizzazione del file:', error);
    setStatus(error.message || 'Errore nella preparazione dell’immagine.');
  }
}

function resetPreview() {
  currentFile = null;
  fileInput.value = '';
  previewImage.removeAttribute('src');
  previewName.textContent = 'Immagine pronta';
  previewCard.hidden = true;

  dropzone.classList.remove('has-file', 'dragover');

  if (previewObjectUrl) {
    URL.revokeObjectURL(previewObjectUrl);
    previewObjectUrl = null;
  }

  if (remotePreviewUrl) {
    URL.revokeObjectURL(remotePreviewUrl);
    remotePreviewUrl = null;
  }

  generatedCode = null;

  if (publicCodeField) publicCodeField.value = '';
  if (paypalSection) paypalSection.hidden = true;
  if (paypalButtonsContainer) paypalButtonsContainer.innerHTML = '';

  setStatus('Carica un’immagine per iniziare.');
  updateSubmitState();
}

function validateFile(file) {
  if (!file) return 'Nessun file selezionato.';
  if (!file.type.startsWith('image/')) return 'Carica un file immagine valido.';
  if (file.size > 15 * 1024 * 1024) return 'Il file supera 15 MB.';

  // 🔥 NUOVO: controllo dimensioni reali
  return new Promise((resolve) => {
    const img = new Image();
    const url = URL.createObjectURL(file);

    img.onload = () => {
      URL.revokeObjectURL(url);

      const maxDim = Math.max(img.width, img.height);

      if (maxDim > 4000) {
        resolve('Immagine troppo grande (max 4000px).');
      } else {
        resolve(null);
      }
    };

    img.onerror = () => resolve('Errore lettura immagine.');
    img.src = url;
  });
}

/* ------------------ FORM DATA ------------------ */

function collectFormData() {
  const formData = new FormData();
  formData.append('file', currentFile);

  const widthInput = generatorForm.querySelector('input[name="width"]');
  const heightInput = generatorForm.querySelector('input[name="height"]');

    // 🔥 HARD LIMIT FRONTEND (ANTI-BYPASS)
  const MAX = 512;
  
  let w = parseInt(widthInput.value, 10);
  let h = parseInt(heightInput.value, 10);
  
  if (!Number.isFinite(w)) w = 16;
  if (!Number.isFinite(h)) h = 16;
  
  if (w > MAX) w = MAX;
  if (h > MAX) h = MAX;
  
  widthInput.value = w;
  heightInput.value = h;
  
  if (widthInput) updateDimensionDisplay(widthInput);
  if (heightInput) updateDimensionDisplay(heightInput);

  const data = new FormData(generatorForm);

  for (const [key, value] of data.entries()) {
    if (['dither', 'generate_pdf', 'generate_stud_preview', 'piece_aware_palette'].includes(key)) {
      formData.append(key, 'on');
    } else {
      formData.append(key, value);
    }
  }

  ['dither', 'generate_pdf', 'generate_stud_preview', 'piece_aware_palette'].forEach((key) => {
    if (!data.has(key)) formData.append(key, 'off');
  });

  return formData;
}

/* ------------------ PREVIEW ------------------ */

async function loadRemotePreview() {
  const formData = collectFormData();

  const response = await apiFetch(`${apiBase}/api/preview`, {
    method: 'POST',
    body: formData
  }, 'preview');

  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || 'Errore preview.');
  }

  const blob = await response.blob();

  if (remotePreviewUrl) URL.revokeObjectURL(remotePreviewUrl);
  remotePreviewUrl = URL.createObjectURL(blob);

  previewImage.src = remotePreviewUrl;
  previewName.textContent = `${currentFile.name} · preview mosaico`;
}

if (previewButton) {
  previewButton.addEventListener('click', async () => {
    if (!currentFile) return;

    try {
      setStatus('Genero preview...');
      await loadRemotePreview();
      setStatus('Preview pronta.');
    } catch (error) {
      setStatus(error.message || 'Errore preview.');
    }
  });
}

/* ------------------ GENERATE CODE ------------------ */

generatorForm.addEventListener('submit', async (event) => {
  event.preventDefault();

  const error = await validateFile(currentFile);
  if (error) {
    setStatus(error);
    return;
  }

  const formData = collectFormData();

  setLoadingState(true);
  setStatus('Generazione codice...');
  resultPanel.hidden = true;

  try {
    const res = await apiFetch(`${apiBase}/api/prepare-package`, {
      method: 'POST',
      body: formData
    }, 'prepare-package');

    if (!res.ok) {
      const payload = await res.json().catch(() => ({}));
      throw new Error(payload.detail || 'Errore generazione.');
    }

    const data = await res.json();

    generatedCode = data.code;

    setLoadingState(false);
    setStatus('Codice generato.');

    resultPanel.hidden = false;

    if (publicCodeField) publicCodeField.value = generatedCode;
    resultMeta.textContent = `Codice: ${generatedCode}`;
    resultPreviewText.textContent =
      'Paga con PayPal oppure inserisci il codice ricevuto dallo staff nel campo di recupero in basso.';

    if (paypalSection) paypalSection.hidden = false;

    renderPayPal();
  } catch (err) {
    setLoadingState(false);
    setStatus(err.message || 'Errore generazione.');
  }
});

/* ------------------ COPY CODE ------------------ */

if (copyCodeButton) {
  copyCodeButton.addEventListener('click', async () => {
    if (!publicCodeField || !publicCodeField.value) return;

    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(publicCodeField.value);
      } else {
        publicCodeField.select();
        document.execCommand('copy');
      }
      setStatus('Codice copiato.');
    } catch {
      setStatus('Impossibile copiare il codice.');
    }
  });
}

/* ------------------ PAYPAL ------------------ */

function renderPayPal() {
  if (!paypalButtonsContainer) return;

  paypalButtonsContainer.innerHTML = '';

  if (typeof paypal === 'undefined') {
    setStatus('PayPal non disponibile al momento.');
    return;
  }

  if (!generatedCode || !generatedCode.startsWith('LEO-')) {
  setStatus('Codice non valido.');
  return;
}

paypal.Buttons({
    createOrder: (data, actions) => {
  return actions.order.create({
    purchase_units: [{
      amount: { value: '5.00' }
    }]
  });
},

    onApprove: async (data, actions) => {
  try {
    const capture = await actions.order.capture();

    setStatus('Pagamento confermato...');

    const res = await fetch(`${apiBase}/api/confirm-payment`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        code: generatedCode,
        order_id: data.orderID,
        paypal_capture_id: capture.id
      })
    });

        if (!res.ok) {
          const payload = await res.json().catch(() => ({}));
          throw new Error(payload.detail || 'Errore conferma pagamento.');
        }

        const result = await res.json();

        setStatus('Download in corso...');
        await downloadPackage(result.redeem_token);
      } catch (error) {
        setStatus(error.message || 'Errore durante il pagamento.');
      }
    },

    onError: () => {
      setStatus('Errore PayPal.');
    }
  }).render('#paypalButtonsContainer');
}

function openCrop(file) {
  rawFile = file;

  const url = URL.createObjectURL(file);

  cropImage.onload = () => {
  if (cropper) {
    cropper.destroy();
    cropper = null;
  }

  cropper = new Cropper(cropImage, {
    viewMode: 1,
    autoCropArea: 1,
    background: false,
    responsive: true,
    checkOrientation: false,
    movable: true,
    zoomable: true,
    scalable: false,
    rotatable: false,
    dragMode: 'move'
  });

  URL.revokeObjectURL(url);
};

  cropImage.src = url;
  cropModal.hidden = false;
}

function gcd(a, b) {
  return b === 0 ? a : gcd(b, a % b);
}

function updateDimensionsFromCrop(w, h) {
  const divisor = gcd(w, h);

  let ratioW = Math.round(w / divisor);
  let ratioH = Math.round(h / divisor);

  const MAX_RATIO_SIDE = 10;

  if (ratioW > MAX_RATIO_SIDE || ratioH > MAX_RATIO_SIDE) {
    const scale = Math.max(ratioW, ratioH) / MAX_RATIO_SIDE;
    ratioW = Math.max(1, Math.round(ratioW / scale));
    ratioH = Math.max(1, Math.round(ratioH / scale));
  }

  const widthInput = generatorForm.querySelector('input[name="width"]');
  const heightInput = generatorForm.querySelector('input[name="height"]');

  widthInput.value = ratioW * 16;
  heightInput.value = ratioH * 16;

  updateDimensionDisplay(widthInput);
  updateDimensionDisplay(heightInput);

  console.log("📐 Ratio normalizzato:", ratioW + ":" + ratioH);
}

cropConfirm.addEventListener('click', async () => {
  if (!cropper) return;

  const canvas = cropper.getCroppedCanvas({
    fillColor: '#ffffff'
  });

  const blob = await new Promise((resolve, reject) => {
    canvas.toBlob((b) => {
      if (!b) {
        reject(new Error('Impossibile creare il crop.'));
        return;
      }
      resolve(b);
    }, 'image/jpeg', 0.9);
  });

  const croppedFile = new File(
    [blob],
    rawFile.name.replace(/\.[^.]+$/, '') + '.jpg',
    { type: 'image/jpeg', lastModified: Date.now() }
  );

  const dt = new DataTransfer();
  dt.items.add(croppedFile);
  fileInput.files = dt.files;

  await setPreview(croppedFile);
  updateDimensionsFromCrop(canvas.width, canvas.height);
  updateSubmitState();
  setStatus(`${rawFile.name} selezionato.`);

  cropModal.hidden = true;
  cropper.destroy();
  cropper = null;
});

cropCancel.addEventListener('click', () => {
  cropModal.hidden = true;
  if (cropper) cropper.destroy();
  cropper = null;
});

/* ------------------ REDEEM ------------------ */

if (redeemButton) {
  redeemButton.addEventListener('click', async () => {
    const value = redeemInput.value.trim();

    if (value.startsWith('LEO-')) {
      alert('Completa il pagamento prima oppure inserisci il codice RDM ricevuto dallo staff.');
      return;
    }

    if (!value.startsWith('RDM-')) {
      alert('Codice non valido');
      return;
    }

    setStatus('Download in corso...');
    await downloadPackage(value);
  });
}

/* ------------------ EVENTS ------------------ */

fileInput.addEventListener('change', (event) => {
  console.log("FILE CHANGE TRIGGERED");

  const file = event.target.files?.[0];
  console.log("FILE:", file);

  if (!file) return;

  openCrop(file);
});

['dragenter', 'dragover'].forEach((eventName) => {
  dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropzone.classList.add('dragover');
  });
});

['dragleave', 'drop'].forEach((eventName) => {
  dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropzone.classList.remove('dragover');
  });
});

dropzone.addEventListener('drop', (event) => {
  const file = event.dataTransfer?.files?.[0];
  if (file) {
    openCrop(file);
  }
});

removeImageButton.addEventListener('click', resetPreview);

menuButton.addEventListener('click', () => {
  const expanded = menuButton.getAttribute('aria-expanded') === 'true';
  menuButton.setAttribute('aria-expanded', String(!expanded));
  mobileMenu.classList.toggle('open');
});

/* ------------------ INIT ------------------ */

if (manualConfirmButton) {
  manualConfirmButton.remove();
}

updateSubmitState();
initHeroPixels();
initReveal();
initDimensionInputs();
console.log("JS CARICATO");