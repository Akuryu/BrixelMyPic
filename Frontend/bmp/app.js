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

/* ------------------ HELPERS ------------------ */

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

function setPreview(file) {
  currentFile = file;

  if (previewObjectUrl) URL.revokeObjectURL(previewObjectUrl);
  if (remotePreviewUrl) {
    URL.revokeObjectURL(remotePreviewUrl);
    remotePreviewUrl = null;
  }

  previewObjectUrl = URL.createObjectURL(file);
  previewImage.src = previewObjectUrl;
  previewName.textContent = file.name;

  previewCard.hidden = false;
  dropzone.classList.add('has-file');

  setStatus(`${file.name} selezionato.`);
  updateSubmitState();
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
  return null;
}

/* ------------------ FORM DATA ------------------ */

function collectFormData() {
  const formData = new FormData();
  formData.append('file', currentFile);

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

  const response = await fetch(`${apiBase}/api/preview`, {
    method: 'POST',
    body: formData
  });

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

  const error = validateFile(currentFile);
  if (error) {
    setStatus(error);
    return;
  }

  const formData = collectFormData();

  setLoadingState(true);
  setStatus('Generazione codice...');
  resultPanel.hidden = true;

  try {
    const res = await fetch(`${apiBase}/api/prepare-package`, {
      method: 'POST',
      body: formData
    });

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
        await actions.order.capture();

        setStatus('Pagamento confermato...');

        const res = await fetch(`${apiBase}/api/confirm-payment`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ code: generatedCode })
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
  const file = event.target.files?.[0];
  if (file) setPreview(file);
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
    const dt = new DataTransfer();
    dt.items.add(file);
    fileInput.files = dt.files;
    setPreview(file);
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