const apiBase = (window.LEOBRICK_API_BASE || '').replace(/\/$/, '');
const fileInput = document.getElementById('fileInput');
const dropzone = document.getElementById('dropzone');
const previewCard = document.getElementById('previewCard');
const previewImage = document.getElementById('previewImage');
const previewName = document.getElementById('previewName');
const removeImageButton = document.getElementById('removeImage');
const generatorForm = document.getElementById('generatorForm');
const submitButton = document.getElementById('submitButton');
const statusText = document.getElementById('statusText');
const progressWrap = document.getElementById('progressWrap');
const progressBar = document.getElementById('progressBar');
const resultPanel = document.getElementById('resultPanel');
const downloadButton = document.getElementById('downloadButton');
const resultMeta = document.getElementById('resultMeta');
const resultPreviewText = document.getElementById('resultPreviewText');
const menuButton = document.getElementById('menuButton');
const mobileMenu = document.getElementById('mobileMenu');
const uploadBadge = document.getElementById('uploadBadge');
const buttonLabel = submitButton.querySelector('.button-label');

let currentFile = null;
let progressTimer = null;
let previewObjectUrl = null;

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

function updateSubmitState() {
  submitButton.disabled = !currentFile;
  uploadBadge.textContent = currentFile ? 'File pronto' : 'Nessun file';
  uploadBadge.classList.toggle('is-ready', Boolean(currentFile));
}

function setStatus(message) {
  statusText.textContent = message;
}

function setLoadingState(isLoading) {
  submitButton.classList.toggle('is-loading', isLoading);
  submitButton.disabled = isLoading || !currentFile;
  buttonLabel.textContent = isLoading ? 'Generazione in corso' : 'Genera mosaico';
}

function setPreview(file) {
  currentFile = file;

  if (previewObjectUrl) {
    URL.revokeObjectURL(previewObjectUrl);
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

  setStatus('Carica un’immagine per iniziare.');
  updateSubmitState();
}

function validateFile(file) {
  if (!file) return 'Nessun file selezionato.';
  if (!file.type.startsWith('image/')) return 'Carica un file immagine valido.';
  if (file.size > 15 * 1024 * 1024) return 'Il file supera 15 MB.';
  return null;
}

function startFakeProgress() {
  progressWrap.hidden = false;
  let value = 6;
  progressBar.style.width = `${value}%`;
  clearInterval(progressTimer);

  progressTimer = setInterval(() => {
    value = Math.min(value + Math.random() * 11, 92);
    progressBar.style.width = `${value}%`;
  }, 260);
}

function stopFakeProgress(done = true) {
  clearInterval(progressTimer);
  progressTimer = null;
  progressBar.style.width = done ? '100%' : '0%';

  setTimeout(() => {
    progressWrap.hidden = true;
    if (!done) {
      progressBar.style.width = '0%';
    }
  }, 450);
}

function handleIncomingFile(file, syncInput = false) {
  const error = validateFile(file);
  if (error) {
    setStatus(error);
    return;
  }

  if (syncInput && file) {
    const dt = new DataTransfer();
    dt.items.add(file);
    fileInput.files = dt.files;
  }

  setPreview(file);
}

fileInput.addEventListener('change', (event) => {
  const file = event.target.files?.[0];
  handleIncomingFile(file);
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
  handleIncomingFile(file, true);
});

removeImageButton.addEventListener('click', resetPreview);

menuButton.addEventListener('click', () => {
  const expanded = menuButton.getAttribute('aria-expanded') === 'true';
  menuButton.setAttribute('aria-expanded', String(!expanded));
  mobileMenu.classList.toggle('open');
});

mobileMenu.querySelectorAll('a').forEach((link) => {
  link.addEventListener('click', () => {
    mobileMenu.classList.remove('open');
    menuButton.setAttribute('aria-expanded', 'false');
  });
});

generatorForm.addEventListener('submit', async (event) => {
  event.preventDefault();

  if (!apiBase || apiBase.includes('tuodominio.it')) {
    setStatus('Servizio temporaneamente non disponibile.');
    return;
  }

  const error = validateFile(currentFile);
  if (error) {
    setStatus(error);
    return;
  }

  const formData = new FormData();
  formData.append('file', currentFile);

  const data = new FormData(generatorForm);
  for (const [key, value] of data.entries()) {
    if (key === 'dither' || key === 'generate_pdf' || key === 'generate_stud_preview' || key === 'piece_aware_palette') {
      formData.append(key, 'on');
    } else {
      formData.append(key, value);
    }
  }

  ['dither', 'generate_pdf', 'generate_stud_preview', 'piece_aware_palette'].forEach((key) => {
    if (!data.has(key)) formData.append(key, 'off');
  });

  setLoadingState(true);
  setStatus('Elaborazione in corso...');
  resultPanel.hidden = true;
  startFakeProgress();

  try {
    const response = await fetch(`${apiBase}/api/generate`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || `Errore API (${response.status})`);
    }

    const payload = await response.json();
    stopFakeProgress(true);
    setLoadingState(false);
    setStatus('Generazione completata.');

    resultPanel.hidden = false;
    downloadButton.href = payload.download_url;
    resultMeta.textContent = `Dimensione finale ${payload.width}×${payload.height} — ${payload.piece_type} — ${payload.palette_size} colori disponibili.`;
    resultPreviewText.textContent = `Job ${payload.job_id} pronto. Scarica lo ZIP per ottenere immagini, istruzioni e file finali.`;
    resultPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (errorObj) {
    stopFakeProgress(false);
    setLoadingState(false);
    setStatus(errorObj.message || 'Errore imprevisto.');
  }
});

document.querySelectorAll('.magnetic').forEach((button) => {
  button.addEventListener('mousemove', (event) => {
    if (button.disabled) return;
    const rect = button.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width - 0.5) * 12;
    const y = ((event.clientY - rect.top) / rect.height - 0.5) * 12;
    button.style.transform = `translate(${x}px, ${y}px)`;
  });

  button.addEventListener('mouseleave', () => {
    button.style.transform = 'translate(0, 0)';
  });
});

updateSubmitState();
initHeroPixels();
initReveal();
