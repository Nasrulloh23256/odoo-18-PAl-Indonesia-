# -*- coding: utf-8 -*-  # Menentukan encoding file Python.

{  # Konfigurasi utama modul data_kapal.
    'name': 'Data Kapal dan Proyek',  # Nama aplikasi yang tampil di menu Apps.
    'summary': 'CRUD data dasar kapal/proyek untuk kebutuhan dokumen TPTR',  # Ringkasan fitur modul.
    # Deskripsi panjang modul yang tampil pada halaman detail Apps.
    'description': "Modul input data kapal/proyek TPTR dengan master kelas kapal yang dapat dipilih.",
    'version': '1.0.0',  # Versi modul.
    'author': 'Palindonesia',  # Pembuat modul.
    'category': 'Operations',  # Kategori aplikasi.
    'sequence': 2,  # Urutan aplikasi di daftar Apps.
    'license': 'LGPL-3',  # Lisensi modul.
    'depends': ['base', 'website'],  # Dependensi ORM + website untuk halaman form CRUD berbasis web.
    'data': [  # File yang dimuat saat instalasi/update modul.
        'security/ir.model.access.csv',  # Aturan hak akses CRUD.
        'views/views.xml',  # Definisi list/form/search, action, dan menu.
        'views/dokumen_pendukung_views.xml',  # View & menu fitur dokumen pendukung TPTR.
        'views/review_persetujuan_views.xml',  # View & menu fitur review/persetujuan TPTR.
        'views/tptr_cover_sheet.xml',  # QWeb template + action report PDF cover sheet TPTR.
        'views/templates.xml',  # Template website untuk CRUD via web form.
        # JRXML tidak dimuat lewat manifest data; file dipakai Jasper Server eksternal.
        # report/report_templates.xml juga tidak dimuat karena alur download PDF memakai REST Jasper.
    ],
    # Asset frontend untuk menyesuaikan warna aksen footer website ke palet navy PAL.
    'assets': {
        'web.assets_frontend': [
            'data_kapal/static/src/css/website_navy.css',
        ],
    },
    'application': True,  # Modul muncul sebagai aplikasi di dashboard Apps.
    'installable': True,  # Modul bisa di-install.
}
