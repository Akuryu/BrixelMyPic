# Frontend LeoBrick

Frontend statico pronto per Aruba.

## Dove impostare il link del server Proxmox
Apri `config.js` e sostituisci:

```js
window.LEOBRICK_API_BASE = 'https://api.tuodominio.it';
```

con il tuo dominio o IP pubblico, per esempio:

```js
window.LEOBRICK_API_BASE = 'https://api.leobrick.com';
```

## File da caricare su Aruba
Carica **tutto il contenuto** di questa cartella sul tuo spazio web:
- `index.html`
- `styles.css`
- `app.js`
- `config.js`

## API richieste dal frontend
- `GET /api/health`
- `POST /api/generate`
- `GET /downloads/{job_id}`