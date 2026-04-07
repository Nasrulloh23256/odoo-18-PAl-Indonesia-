## Januari 2026

1. Judul: Analisis awal proyek custom addons Odoo
Tanggal: 26 Januari 2026
Waktu Kegiatan: 640 menit
Uraian: Menyusun rencana kerja pengembangan dua modul custom (`asset_register` sebagai pembelajaran CRUD dan `data_kapal/TPTR` sebagai modul utama), termasuk penetapan struktur folder, model data, dan target fitur per fase.
Bukti Kegiatan: file: `Pal_Indonesia/asset_register/__manifest__.py`

2. Judul: Inisialisasi modul pembelajaran Asset Register
Tanggal: 27 Januari 2026
Waktu Kegiatan: 640 menit
Uraian: Menyiapkan scaffold awal modul `asset_register`, menyusun dependensi dasar, dan menyiapkan file inti model, view, controller, serta security agar modul siap dipakai untuk latihan CRUD.
Bukti Kegiatan: file: `Pal_Indonesia/asset_register/models/models.py`

3. Judul: Implementasi model dan CRUD dasar Asset Register
Tanggal: 28 Januari 2026
Waktu Kegiatan: 640 menit
Uraian: Mengembangkan model data inti dan alur input/edit/hapus data di backend Odoo, termasuk pemetaan field utama yang dibutuhkan untuk simulasi modul bisnis.
Bukti Kegiatan: file: `Pal_Indonesia/asset_register/models/location.py`

4. Judul: Konfigurasi hak akses dan stabilisasi modul Asset Register
Tanggal: 29 Januari 2026
Waktu Kegiatan: 640 menit
Uraian: Menyusun access control untuk user internal, merapikan menu dan action, serta menyesuaikan deklarasi data agar instalasi dan upgrade modul berjalan konsisten.
Bukti Kegiatan: file: `Pal_Indonesia/asset_register/security/ir.model.access.csv`

5. Judul: Review hasil pembelajaran CRUD dan transisi ke modul TPTR
Tanggal: 30 Januari 2026
Waktu Kegiatan: 640 menit
Uraian: Menutup fase pembelajaran `asset_register`, melakukan review struktur coding standar Odoo, lalu menyiapkan backlog teknis untuk pengembangan modul TPTR berbasis kebutuhan dokumen cover.
Bukti Kegiatan: file: `Pal_Indonesia/asset_register/controllers/pal_theme.py`

## Februari 2026

1. Judul: Inisialisasi modul TPTR (Data Kapal)
Tanggal: 2 Februari 2026
Waktu Kegiatan: 640 menit
Uraian: Membuat kerangka modul `data_kapal`, menyusun manifest, struktur models/views/controllers, dan baseline konfigurasi untuk pengembangan berkelanjutan.
Bukti Kegiatan: file: `Pal_Indonesia/data_kapal/__manifest__.py`

2. Judul: Implementasi model Data Kapal & Proyek
Tanggal: 3 Februari 2026
Waktu Kegiatan: 640 menit
Uraian: Membangun model utama `pal.kapal.proyek` dengan field penting (nama kapal, nomor proyek, kelas kapal, delegasi pemilik, jenis tes, tanggal input) sebagai sumber data inti TPTR.
Bukti Kegiatan: file: `Pal_Indonesia/data_kapal/models/models.py`

3. Judul: Penyusunan view list/form/search Data Kapal
Tanggal: 4 Februari 2026
Waktu Kegiatan: 640 menit
Uraian: Mengembangkan tampilan backend untuk CRUD penuh data kapal/proyek serta menyiapkan action dan menu agar alur input user internal lebih terstruktur.
Bukti Kegiatan: file: `Pal_Indonesia/data_kapal/views/views.xml`

4. Judul: Penambahan master Kelas Kapal
Tanggal: 5 Februari 2026
Waktu Kegiatan: 640 menit
Uraian: Menambahkan model master kelas kapal dan relasi ke data proyek untuk memastikan input kelas kapal konsisten melalui dropdown terkontrol.
Bukti Kegiatan: file: `Pal_Indonesia/data_kapal/models/models.py`

5. Judul: Penyesuaian security dan validasi akses modul TPTR
Tanggal: 6 Februari 2026
Waktu Kegiatan: 640 menit
Uraian: Menetapkan rule akses CRUD untuk model TPTR agar user internal dapat mengelola data dengan aman dan sesuai role aplikasi.
Bukti Kegiatan: file: `Pal_Indonesia/data_kapal/security/ir.model.access.csv`

6. Judul: Pengembangan halaman website CRUD Data Kapal
Tanggal: 9 Februari 2026
Waktu Kegiatan: 640 menit
Uraian: Menyusun endpoint website untuk menampilkan dan mengelola data kapal/proyek dari sisi web, termasuk alur create/update/delete yang terhubung ke model backend.
Bukti Kegiatan: file: `Pal_Indonesia/data_kapal/controllers/controllers.py`

7. Judul: Implementasi template dan form website TPTR
Tanggal: 10 Februari 2026
Waktu Kegiatan: 640 menit
Uraian: Menyusun tampilan form dan tabel data TPTR pada website untuk mendukung input operasional non-backend dengan alur yang tetap terkontrol.
Bukti Kegiatan: file: `Pal_Indonesia/data_kapal/views/templates.xml`

8. Judul: Penyesuaian branding dan style navy
Tanggal: 11 Februari 2026
Waktu Kegiatan: 640 menit
Uraian: Menyesuaikan logo perusahaan dan palet warna agar tampilan website TPTR sesuai identitas visual PAL, termasuk penataan elemen header/footer.
Bukti Kegiatan: file: `Pal_Indonesia/data_kapal/static/src/css/website_navy.css`

9. Judul: Troubleshooting konfigurasi database dan environment
Tanggal: 12 Februari 2026
Waktu Kegiatan: 640 menit
Uraian: Menangani kendala koneksi PostgreSQL/collation, menyesuaikan parameter database aktif (`odoo18`), dan memastikan proses startup Odoo kembali stabil.
Bukti Kegiatan: file: `odoo.conf`

10. Judul: Implementasi modul Lokasi & Kelas Pengujian
Tanggal: 13 Februari 2026
Waktu Kegiatan: 640 menit
Uraian: Menambahkan model `tptr.lokasi_kelas`, relasi ke data kapal, serta tampilan list/form untuk pencatatan lokasi pengujian dan status sign class.
Bukti Kegiatan: file: `Pal_Indonesia/data_kapal/models/lokasi_kelas.py`

11. Judul: Implementasi modul Dokumen Pendukung
Tanggal: 18 Februari 2026
Waktu Kegiatan: 640 menit
Uraian: Menambahkan model `tptr.dokumen_pendukung` berikut relasi ke proyek, validasi field wajib, dan integrasi ke tampilan form Data Kapal.
Bukti Kegiatan: file: `Pal_Indonesia/data_kapal/models/dokumen_pendukung.py`

12. Judul: Implementasi modul Review & Persetujuan
Tanggal: 19 Februari 2026
Waktu Kegiatan: 640 menit
Uraian: Mengembangkan model `tptr.review_persetujuan` untuk status review internal, review class/owner, dan status tanda tangan agar proses approval terdokumentasi.
Bukti Kegiatan: file: `Pal_Indonesia/data_kapal/models/review_persetujuan.py`

13. Judul: Pengembangan template cover TPTR berbasis Jasper
Tanggal: 20 Februari 2026
Waktu Kegiatan: 640 menit
Uraian: Melanjutkan penyusunan layout `cover_sheet_report.jrxml`, menyelaraskan grid tabel, area logo, rev block, serta elemen visual agar mendekati format dokumen cover standar.
Bukti Kegiatan: file: `Pal_Indonesia/data_kapal/report/cover_sheet_report.jrxml`

14. Judul: Integrasi service Odoo ke JasperReports
Tanggal: 23 Februari 2026
Waktu Kegiatan: 640 menit
Uraian: Menyusun service model untuk mengeksekusi report melalui REST Jasper, termasuk pemetaan parameter data proyek dari Odoo ke report unit Jasper Server.
Bukti Kegiatan: file: `Pal_Indonesia/data_kapal/models/report.py`

15. Judul: Pengembangan wizard step-by-step pengisian cover TPTR
Tanggal: 24 Februari 2026
Waktu Kegiatan: 640 menit
Uraian: Membuat alur web wizard 4 langkah (Data Kapal, Lokasi & Kelas, Dokumen Pendukung, Review & Persetujuan) dengan validasi berurutan agar user tidak melompati step.
Bukti Kegiatan: file: `Pal_Indonesia/data_kapal/controllers/controllers.py`

16. Judul: Perbaikan konfigurasi parameter Jasper dan autentikasi
Tanggal: 25 Februari 2026
Waktu Kegiatan: 640 menit
Uraian: Menormalkan nilai system parameter Jasper (`base_url`, `report_unit`, username/password), memvalidasi URI report repository, dan memastikan request tidak lagi gagal karena konfigurasi.
Bukti Kegiatan: file: `Pal_Indonesia/data_kapal/models/models.py`

17. Judul: Integrasi simbol proyek dinamis pada cover
Tanggal: 26 Februari 2026
Waktu Kegiatan: 640 menit
Uraian: Menambahkan dukungan upload `project_symbol` dari data proyek, mengirimkan URL gambar ke Jasper, serta menyiapkan fallback image agar render report tetap stabil saat simbol belum diunggah.
Bukti Kegiatan: file: `Pal_Indonesia/data_kapal/models/models.py`

18. Judul: Uji akhir alur TPTR dan dokumentasi hasil implementasi
Tanggal: 27 Februari 2026
Waktu Kegiatan: 640 menit
Uraian: Melakukan validasi end-to-end alur input data sampai unduh PDF cover, upgrade modul berulang untuk verifikasi stabilitas, dan merapikan catatan implementasi sebagai dokumentasi kerja.
Bukti Kegiatan: file: `Pal_Indonesia/data_kapal/report/cover_sheet_report.jrxml`

---

Catatan hari libur tanpa kegiatan pada rentang 26 Januari 2026 s.d. 28 Februari 2026:
- Sabtu dan Minggu.
- 16 Februari 2026 (Cuti Bersama Tahun Baru Imlek 2577 Kongzili).
- 17 Februari 2026 (Tahun Baru Imlek 2577 Kongzili).
