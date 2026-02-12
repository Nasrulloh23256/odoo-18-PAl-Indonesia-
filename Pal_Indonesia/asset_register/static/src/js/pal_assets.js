/*
  Script ini mengaktifkan debounce pada form filter /pal/assets agar pencarian terasa cepat di sisi user,
  tetapi tetap ramah server. Prinsipnya: ketikan di input ditahan sebentar sebelum submit,
  sementara perubahan select kondisi langsung submit karena itu adalah aksi eksplisit pengguna.
*/
document.addEventListener('DOMContentLoaded', () => {
  /* Bagian inisialisasi elemen: semua selector dikumpulkan di awal agar mudah dicek dan mudah dirawat. */
  const form = document.getElementById('pal-assets-filter');
  if (!form) {
    return;
  }

  const inputQuery = document.getElementById('pal-search-q');
  const inputLocation = document.getElementById('pal-search-location');
  const selectCondition = document.getElementById('pal-search-condition');

  /* Bagian state: simpan timer debounce dan query terakhir untuk mencegah submit berulang yang sama. */
  let debounceTimer = null;
  let lastQuery = null;

  /* Bagian helper: ubah isi form menjadi query string yang konsisten untuk dibandingkan atau dikirim. */
  const buildQuery = () => {
    const params = new URLSearchParams(new FormData(form));
    return params.toString();
  };

  /* Bagian debounce: menunda submit supaya tidak memicu request setiap huruf, namun tetap terasa instan. */
  const submitWithDebounce = (delayMs) => {
    if (debounceTimer) {
      clearTimeout(debounceTimer);
    }
    debounceTimer = setTimeout(() => {
      const currentQuery = buildQuery();
      if (currentQuery === lastQuery) {
        return;
      }
      lastQuery = currentQuery;
      if (form.requestSubmit) {
        form.requestSubmit();
      } else {
        form.submit();
      }
    }, delayMs);
  };

  /* Bagian submit instan: dipakai untuk event yang memang seharusnya langsung berlaku, seperti select kondisi. */
  const submitImmediately = () => {
    if (debounceTimer) {
      clearTimeout(debounceTimer);
    }
    const currentQuery = buildQuery();
    if (currentQuery === lastQuery) {
      return;
    }
    lastQuery = currentQuery;
    if (form.requestSubmit) {
      form.requestSubmit();
    } else {
      form.submit();
    }
  };

  /* Bagian binding event: input teks memakai debounce, select kondisi langsung submit. */
  if (inputQuery) {
    inputQuery.addEventListener('input', () => submitWithDebounce(120));
  }
  if (inputLocation) {
    if (inputLocation.tagName === 'SELECT') {
      inputLocation.addEventListener('change', submitImmediately);
    } else {
      inputLocation.addEventListener('input', () => submitWithDebounce(120));
    }
  }
  if (selectCondition) {
    selectCondition.addEventListener('change', submitImmediately);
  }
});
