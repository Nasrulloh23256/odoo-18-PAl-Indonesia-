# -*- coding: utf-8 -*-  # Menentukan encoding file Python.

{  # Konfigurasi utama modul data_kapal.
    'name': 'Data Kapal dan Proyek',  # Nama aplikasi yang tampil di menu Apps.
    'summary': 'CRUD data dasar kapal/proyek untuk kebutuhan dokumen TPTR',  # Ringkasan fitur modul.
    # Deskripsi panjang modul yang tampil pada halaman detail Apps.
    'description': "Modul input data kapal/proyek TPTR dengan master kelas kapal yang dapat dipilih.",
    'version': '1.0.0',  # Versi modul.
    'author': 'Palindonesia',  # Pembuat modul.
    'category': 'Operations',  # Kategori aplikasi.
    'license': 'LGPL-3',  # Lisensi modul.
    'depends': ['base'],  # Dependensi minimal untuk ORM, view, menu, dan security.
    'data': [  # File yang dimuat saat instalasi/update modul.
        'security/ir.model.access.csv',  # Aturan hak akses CRUD.
        'views/views.xml',  # Definisi list/form/search, action, dan menu.
    ],
    'application': True,  # Modul muncul sebagai aplikasi di dashboard Apps.
    'installable': True,  # Modul bisa di-install.
}
