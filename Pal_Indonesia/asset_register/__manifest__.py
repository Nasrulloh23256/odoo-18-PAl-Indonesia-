# -*- coding: utf-8 -*-  # Menentukan encoding file

{  # Mulai dictionary konfigurasi modul
    'name': 'Asset Register',  # Nama modul yang tampil di Apps
    'summary': 'Simple asset and tool register for CRUD practice',  # Ringkasan singkat modul
    'description': """  # Deskripsi panjang modul (tampil di Module Info)
Asset & Tool Register  # Judul deskripsi
Modul sederhana untuk mencatat aset: nama, kode, lokasi, kondisi, tanggal beli.  # Penjelasan singkat

Fitur:  # Daftar fitur 
- CRUD aset  # Create/Read/Update/Delete
- List & form view  # Tampilan list dan form
- Filter + Group By  # Fitur filter dan grouping
    """,  
    
    'version': '1.0.0',  # Versi modul
    'author': 'Palindonesia',  # Nama pembuat modul
    'website': 'http://localhost:8069/pal/assets',  
    'category': 'Operations',  # Kategori modul di Apps
    'license': 'LGPL-3',  # Lisensi modul
    'sequence': 1,  # Urutan modul di Apps
    'depends': ['base'],  # Modul yang menjadi dependensi
    'data': [  # Daftar file data yang dimuat
        'security/ir.model.access.csv',  # File akses keamanan
        'views/views.xml',  # File view XML
        'views/templates.xml',  # Template UI (QWeb)
        'views/login_logo.xml',  # Override logo login (PAL)
        'data/module_sequence.xml',  # File update sequence modul di Apps
    ],  # Akhir list data
    'application': True,  # Modul muncul sebagai aplikasi
    'installable': True,  # Modul bisa diinstall
    
    'assets': {  # Daftar asset front-end & back-end
        'web.assets_frontend': [  # Asset untuk website
            'asset_register/static/src/css/pal_theme.css',  # CSS tema PAL
            'asset_register/static/src/js/pal_assets.js',  # JS debounce pencarian
        ],  # Akhir asset frontend
        'web.assets_backend': [  # Asset untuk tampilan backend (Apps)
            'asset_register/static/src/css/pal_theme.css',  # CSS tema PAL
        ],  # Akhir asset backend
    },  # Akhir konfigurasi assets

}   
