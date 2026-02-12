from odoo import http
from odoo.http import request


class PalThemeController(http.Controller):
    # Controller ini menjadi pintu utama halaman custom /pal/theme dan /pal/assets agar user bisa CRUD tanpa masuk menu backend.
    # Semua handler di bawah sengaja dibuat sederhana supaya flow Create/Read/Update/Delete mudah dipahami untuk latihan.

    # Route ini hanya mengarahkan /pal/theme ke /pal/assets supaya user langsung melihat halaman CRUD tanpa langkah ekstra.
    @http.route(['/pal/theme'], type='http', auth='user', website=False)
    def pal_theme_page(self, **kwargs):
        return request.redirect('/pal/assets')

    # Helper parsing integer dari query/form agar input id lokasi aman dipakai di domain atau write/create.
    def _safe_int(self, value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    # Handler utama CRUD: menampilkan list aset, menerima input create, dan memproses filter pencarian.
    # Tujuannya agar semua aktivitas dasar (lihat, tambah, cari) bisa dilakukan di satu halaman dengan alur yang konsisten.
    @http.route(['/pal/assets'], type='http', auth='user', website=False, methods=['GET', 'POST'], csrf=True)
    def pal_assets_page(self, **post):
        # Data statis kondisi dipakai untuk select di form dan filter agar label konsisten antara form input dan pencarian.
        conditions = [
            ('baik', 'Baik'),
            ('rusak', 'Rusak'),
            ('perbaikan', 'Perbaikan'),
        ]
        # Daftar lokasi untuk dropdown create/edit/filter dibaca semua agar lokasi baru selalu langsung terlihat.
        locations = request.env['pal.asset.location'].search([], order='name asc')

        # Ambil parameter query dari URL untuk pencarian dan filter, lalu dibersihkan supaya aman dipakai di domain.
        search_query = (request.httprequest.args.get('q') or '').strip()
        filter_condition = (request.httprequest.args.get('condition') or '').strip()
        filter_location_id = self._safe_int(request.httprequest.args.get('location_id'))
        # Error dipisah per form agar user langsung tahu bagian mana yang gagal saat submit.
        asset_error = None
        location_error = None

        # Blok Create: ada dua jenis form di halaman ini (asset dan location), dibedakan pakai hidden input form_type.
        if request.httprequest.method == 'POST':
            form_type = (post.get('form_type') or 'asset').strip()

            # Form tambah lokasi: simpan master lokasi baru agar bisa langsung dipilih di form aset.
            if form_type == 'location':
                location_name = (post.get('location_name') or '').strip()
                location_code = (post.get('location_code') or '').strip()
                if not location_name:
                    location_error = 'Nama Lokasi wajib diisi.'
                else:
                    location_model = request.env['pal.asset.location']
                    existing_location = location_model.search(
                        [('name', '=ilike', location_name)],
                        limit=1,
                    )
                    if existing_location:
                        location_error = 'Nama Lokasi sudah ada, gunakan nama lain.'
                    else:
                        location_model.create({
                            'name': location_name,
                            'code': location_code,
                        })
                        return request.redirect('/pal/assets')
            else:
                # Form tambah aset: validasi field wajib lalu buat data aset baru.
                name = (post.get('name') or '').strip()
                code = (post.get('code') or '').strip()
                location_id = self._safe_int(post.get('location_id'))
                new_location_name = (post.get('new_location_name') or '').strip()
                condition = post.get('condition') or 'baik'
                purchase_date = post.get('purchase_date') or False
                if not name or not code:
                    asset_error = 'Nama Aset dan Kode Aset wajib diisi.'
                else:
                    # Fallback: jika user belum punya lokasi di dropdown, izinkan buat lokasi baru langsung dari form aset.
                    if not location_id and new_location_name:
                        location_model = request.env['pal.asset.location']
                        matched_location = location_model.search(
                            [('name', '=ilike', new_location_name)],
                            limit=1,
                        )
                        if matched_location:
                            location_id = matched_location.id
                        else:
                            created_location = location_model.create({'name': new_location_name})
                            location_id = created_location.id

                    request.env['pal.asset'].create({
                        'name': name,
                        'code': code,
                        'location_id': location_id or False,
                        'condition': condition,
                        'purchase_date': purchase_date,
                    })
                    return request.redirect('/pal/assets')

        # Blok Search/Filter: domain disusun dari keyword dan filter agar hasil list langsung sesuai kriteria user.
        domain = []
        if search_query:
            prefix = f"{search_query}%"
            domain += ['|', '|', ('name', '=ilike', prefix), ('code', '=ilike', prefix), ('location_id.name', '=ilike', prefix)]
        if filter_condition:
            domain += [('condition', '=', filter_condition)]
        if filter_location_id:
            domain += [('location_id', '=', filter_location_id)]

        # Ambil data sesuai domain dan kirim ke template QWeb supaya bisa dirender sebagai tabel.
        assets = request.env['pal.asset'].search(domain, order='id desc')
        return request.render('asset_register.pal_asset_crud_page', {
            'assets': assets,
            'conditions': conditions,
            'locations': locations,
            'asset_error': asset_error,
            'location_error': location_error,
            'search_query': search_query,
            'filter_condition': filter_condition,
            'filter_location_id': filter_location_id,
        })

    # Handler edit: menampilkan form edit dan menyimpan perubahan, supaya update data lebih terarah.
    # Nilai lama ditampilkan kembali agar user hanya mengubah bagian yang diperlukan.
    @http.route(['/pal/assets/<int:asset_id>/edit'], type='http', auth='user', website=False, methods=['GET', 'POST'], csrf=True)
    def pal_assets_edit(self, asset_id, **post):
        asset = request.env['pal.asset'].browse(asset_id)
        if not asset.exists():
            return request.redirect('/pal/assets')
        conditions = [
            ('baik', 'Baik'),
            ('rusak', 'Rusak'),
            ('perbaikan', 'Perbaikan'),
        ]
        # Daftar lokasi dibaca semua agar opsi lokasi pada edit selalu lengkap.
        locations = request.env['pal.asset.location'].search([], order='name asc')
        error = None
        if request.httprequest.method == 'POST':
            name = (post.get('name') or '').strip()
            code = (post.get('code') or '').strip()
            location_id = self._safe_int(post.get('location_id'))
            condition = post.get('condition') or 'baik'
            purchase_date = post.get('purchase_date') or False
            if not name or not code:
                error = 'Nama Aset dan Kode Aset wajib diisi.'
            else:
                asset.write({
                    'name': name,
                    'code': code,
                    'location_id': location_id or False,
                    'condition': condition,
                    'purchase_date': purchase_date,
                })
                return request.redirect('/pal/assets')
        return request.render('asset_register.pal_asset_edit_page', {
            'asset': asset,
            'conditions': conditions,
            'locations': locations,
            'error': error,
        })

    # Handler delete: menghapus record dan kembali ke list, agar proses hapus tetap sederhana dan jelas.
    # Dipisah sendiri supaya aksi destructive tetap eksplisit dan mudah dilacak.
    @http.route(['/pal/assets/<int:asset_id>/delete'], type='http', auth='user', website=False, methods=['POST'], csrf=True)
    def pal_assets_delete(self, asset_id, **post):
        asset = request.env['pal.asset'].browse(asset_id)
        if asset.exists():
            asset.unlink()
        return request.redirect('/pal/assets')
